# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# to configure behavior, define $CQL_TEST_HOST to the destination address
# and $CQL_TEST_PORT to the associated port.

import csv
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from cassandra import ConsistencyLevel, OperationTimedOut, WriteTimeout, WriteType
from cassandra.metadata import MIN_LONG, Murmur3Token
from cassandra.policies import RetryPolicy, WhiteListRoundRobinPolicy

from cqlshlib.copyutil import (CopyTask, ExpBackoffRetryPolicy, ExportProcess, ExportTask, FastTokenAwarePolicy,
                               ImportProcess, ImportProcessResult, ImportTask, ImportTaskError)


Default = object()


class CopyTaskTest(unittest.TestCase):

    def setUp(self):
        # set up default test data
        self.ks = 'testks'
        self.table = 'testtable'
        self.columns = ['a', 'b']
        self.fname = 'test_fname'
        self.opts = {}
        self.protocol_version = 0
        self.config_file = 'test_config'
        # Create mock hosts with addresses
        self.hosts = []
        for ip in ['10.0.0.1', '10.0.0.2', '10.0.0.3', '10.0.0.4']:
            host = Mock()
            host.address = ip
            host.datacenter = 'dc1'
            host.is_up = True
            self.hosts.append(host)

    def mock_shell(self):
        """
        Set up a mock Shell so we can unit test ExportTask and ImportTask internals
        """
        shell = Mock()
        shell.conn = Mock()
        shell.conn.get_control_connection_host.return_value = self.hosts[0]
        shell.conn.connect_timeout = 5
        shell.conn.cql_version = '3.4.5'
        shell.conn.metadata.all_hosts.return_value = self.hosts
        shell.get_column_names.return_value = self.columns
        shell.debug = False
        shell.coverage = False
        shell.coveragerc_path = None
        shell.port = 9042
        shell.ssl = None
        shell.auth_provider = None
        shell.client_routes_config = None
        shell.contact_points = (self.hosts[0].address,)
        shell.consistency_level = 'ONE'
        shell.display_timestamp_format = 'DEFAULT_TIMESTAMP_FORMAT'
        shell.display_date_format = 'DEFAULT_DATE_FORMAT'
        shell.display_nanotime_format = 'DEFAULT_NANOTIME_FORMAT'

        # Mock table_meta with columns and primary_key
        table_meta = Mock()
        table_meta.columns = {col: Mock() for col in self.columns}
        primary_key_col = Mock()
        primary_key_col.name = self.columns[0]  # First column as primary key
        table_meta.primary_key = [primary_key_col]
        shell.get_table_meta.return_value = table_meta

        return shell


class TestGetHost(CopyTaskTest):
    """
    CopyTask.get_host picks the host whose datacenter becomes local_dc, which decides which
    replicas COPY talks to, so the pick must not depend on driver metadata iteration order.
    """

    def mock_shell_without_control_host(self):
        shell = self.mock_shell()
        shell.conn.get_control_connection_host.return_value = None
        shell.client_routes_config = object()
        shell.contact_points = ('proxy-a.example.com',)
        return shell

    def test_returns_control_connection_host_when_available(self):
        shell = self.mock_shell()
        self.assertIs(CopyTask.get_host(shell), self.hosts[0])
        shell.conn.metadata.all_hosts.assert_not_called()

    def test_returns_none_without_client_routes(self):
        shell = self.mock_shell()
        shell.conn.get_control_connection_host.return_value = None

        self.assertIsNone(CopyTask.get_host(shell))
        shell.conn.metadata.all_hosts.assert_not_called()

    def test_is_deterministic_regardless_of_metadata_order(self):
        shell = self.mock_shell_without_control_host()

        shell.conn.metadata.all_hosts.return_value = list(self.hosts)
        first = CopyTask.get_host(shell)
        shell.conn.metadata.all_hosts.return_value = list(reversed(self.hosts))
        second = CopyTask.get_host(shell)

        self.assertIs(first, second)
        self.assertEqual(first.address, '10.0.0.1')

    def test_prefers_a_host_that_is_also_a_contact_point(self):
        shell = self.mock_shell_without_control_host()
        shell.contact_points = ('proxy-a.example.com', self.hosts[2].address)

        self.assertIs(CopyTask.get_host(shell), self.hosts[2])

    def test_skips_down_hosts(self):
        shell = self.mock_shell_without_control_host()
        self.hosts[0].is_up = False
        self.hosts[1].is_up = False

        self.assertIs(CopyTask.get_host(shell), self.hosts[2])

    def test_falls_back_to_a_down_host_when_all_are_down(self):
        shell = self.mock_shell_without_control_host()
        for host in self.hosts:
            host.is_up = False

        self.assertIs(CopyTask.get_host(shell), self.hosts[0])

    def test_warns_when_hosts_span_datacenters(self):
        shell = self.mock_shell_without_control_host()
        self.hosts[2].datacenter = 'dc2'
        self.hosts[3].datacenter = 'dc2'

        self.assertIs(CopyTask.get_host(shell), self.hosts[0])
        shell.printerr.assert_called_once()
        message = shell.printerr.call_args[0][0]
        self.assertIn('10.0.0.1', message)
        self.assertIn('dc1, dc2', message)

    def test_does_not_warn_for_a_single_datacenter(self):
        shell = self.mock_shell_without_control_host()

        self.assertIs(CopyTask.get_host(shell), self.hosts[0])
        shell.printerr.assert_not_called()

    def test_reports_empty_cluster_metadata(self):
        shell = self.mock_shell_without_control_host()
        shell.conn.metadata.all_hosts.return_value = []

        self.assertIsNone(CopyTask.get_host(shell))
        shell.printerr.assert_called_once()


class TestExportTask(CopyTaskTest):

    def _test_get_ranges_murmur3_base(self, opts, expected_ranges, fname=Default):
        """
        Set up a mock shell with a simple token map to test the ExportTask get_ranges function.
        """
        fname = self.fname if fname is Default else fname
        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        # token range for a cluster of 4 nodes with replication factor 3
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }
        # merge override options with standard options
        overridden_opts = dict(self.opts)
        for k, v in opts.items():
            overridden_opts[k] = v
        export_task = ExportTask(shell, self.ks, self.table, self.columns, fname, overridden_opts, self.protocol_version, self.config_file)
        assert export_task.get_ranges() == expected_ranges
        export_task.close()

    def test_get_ranges_murmur3(self):
        """
        Test behavior of ExportTask internal get_ranges function
        """

        # return empty dict and print error if begin_token < min_token
        self._test_get_ranges_murmur3_base({'begintoken': MIN_LONG - 1}, {})

        # return empty dict and print error if begin_token < min_token
        self._test_get_ranges_murmur3_base({'begintoken': 1, 'endtoken': -1}, {})

        # simple case of a single range
        expected_ranges = {(1, 2): {'hosts': ('10.0.0.4', '10.0.0.1', '10.0.0.2'), 'attempts': 0, 'rows': 0, 'workerno': -1}}
        self._test_get_ranges_murmur3_base({'begintoken': 1, 'endtoken': 2}, expected_ranges)

        # simple case of two contiguous ranges
        expected_ranges = {
            (-4611686018427387903, 0): {'hosts': ('10.0.0.3', '10.0.0.4', '10.0.0.1'), 'attempts': 0, 'rows': 0, 'workerno': -1},
            (0, 1): {'hosts': ('10.0.0.4', '10.0.0.1', '10.0.0.2'), 'attempts': 0, 'rows': 0, 'workerno': -1}
        }
        self._test_get_ranges_murmur3_base({'begintoken': -4611686018427387903, 'endtoken': 1}, expected_ranges)

        # specify a begintoken only (endtoken defaults to None)
        expected_ranges = {
            (4611686018427387905, None): {'hosts': ('10.0.0.1', '10.0.0.2', '10.0.0.3'), 'attempts': 0, 'rows': 0, 'workerno': -1}
        }
        self._test_get_ranges_murmur3_base({'begintoken': 4611686018427387905}, expected_ranges)

        # specify an endtoken only (begintoken defaults to None)
        expected_ranges = {
            (None, MIN_LONG + 1): {'hosts': ('10.0.0.2', '10.0.0.3', '10.0.0.4'), 'attempts': 0, 'rows': 0, 'workerno': -1}
        }
        self._test_get_ranges_murmur3_base({'endtoken': MIN_LONG + 1}, expected_ranges)

    def test_exporting_to_std(self):
        self._test_get_ranges_murmur3_base({'begintoken': MIN_LONG - 1}, {}, fname=None)

    def test_make_params_includes_client_routes_for_workers(self):
        shell = self.mock_shell()
        shell.client_routes_config = object()
        shell.contact_points = ('proxy-a.example.com', 'proxy-b.example.com')
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
        }

        export_task = ExportTask(shell, self.ks, self.table, self.columns,
                                 self.fname, {}, self.protocol_version, self.config_file)
        params = export_task.make_params()

        self.assertIs(params['client_routes_config'], shell.client_routes_config)
        self.assertEqual(params['contact_points'], shell.contact_points)
        export_task.close()

    def test_export_process_uses_client_routes_when_connecting_worker(self):
        shell = self.mock_shell()
        shell.client_routes_config = object()
        shell.contact_points = ('proxy-a.example.com', 'proxy-b.example.com')
        shell.ssl = True
        ssl_context = object()
        export_task = ExportTask(shell, self.ks, self.table, self.columns,
                                 self.fname, {}, self.protocol_version, self.config_file)
        export_process = ExportProcess(export_task.update_params(export_task.make_params(), 0))

        with patch('cqlshlib.copyutil.ssl_settings', return_value=ssl_context) as mock_ssl_settings, \
                patch('cqlshlib.copyutil.Cluster') as mock_cluster:
            mock_cluster.return_value.connect.return_value = Mock()

            export_process.connect('10.0.0.2')

        call_kwargs = mock_cluster.call_args[1]
        self.assertEqual(call_kwargs['contact_points'], shell.contact_points)
        self.assertIs(call_kwargs['client_routes_config'], shell.client_routes_config)
        self.assertIsInstance(call_kwargs['load_balancing_policy'], WhiteListRoundRobinPolicy)
        self.assertIs(call_kwargs['ssl_context'], ssl_context)
        mock_ssl_settings.assert_called_once_with('proxy-a.example.com', self.config_file)
        export_task.close()

    def test_get_ranges_uses_metadata_host_when_client_routes_control_host_missing(self):
        shell = self.mock_shell()
        shell.conn.get_control_connection_host.return_value = None
        shell.client_routes_config = object()
        shell.contact_points = ('proxy-a.example.com',)
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.conn.metadata.token_map = None
        shell.conn.metadata.all_hosts.return_value = [self.hosts[1]]

        export_task = ExportTask(shell, self.ks, self.table, self.columns,
                                 self.fname, {}, self.protocol_version, self.config_file)

        self.assertEqual(export_task.get_ranges(), {
            (None, None): {'hosts': ('10.0.0.2',), 'attempts': 0, 'rows': 0, 'workerno': -1}
        })
        export_task.close()


class TestImportTask(CopyTaskTest):
    def test_make_params_uses_metadata_host_when_client_routes_control_host_missing(self):
        shell = self.mock_shell()
        shell.conn.get_control_connection_host.return_value = None
        shell.client_routes_config = object()
        shell.contact_points = ('proxy-a.example.com',)
        shell.conn.metadata.all_hosts.return_value = [self.hosts[2]]

        import_task = ImportTask(shell, self.ks, self.table, self.columns,
                                 self.fname, {}, self.protocol_version, self.config_file)
        params = import_task.make_params()

        self.assertEqual(params['hostname'], '10.0.0.3')
        self.assertEqual(params['local_dc'], 'dc1')
        self.assertIs(params['client_routes_config'], shell.client_routes_config)
        self.assertEqual(params['contact_points'], shell.contact_points)
        import_task.close()

    def test_import_process_uses_client_routes_when_connecting_worker(self):
        shell = self.mock_shell()
        shell.client_routes_config = object()
        shell.contact_points = ('proxy-a.example.com', 'proxy-b.example.com')
        shell.ssl = True
        ssl_context = object()
        import_task = ImportTask(shell, self.ks, self.table, self.columns,
                                 self.fname, {}, self.protocol_version, self.config_file)
        import_process = ImportProcess(import_task.update_params(import_task.make_params(), 0))

        with patch('cqlshlib.copyutil.ssl_settings', return_value=ssl_context) as mock_ssl_settings, \
                patch('cqlshlib.copyutil.Cluster') as mock_cluster:
            session = Mock()
            mock_cluster.return_value.connect.return_value = session

            self.assertIs(import_process.session, session)

        call_kwargs = mock_cluster.call_args[1]
        self.assertEqual(call_kwargs['contact_points'], shell.contact_points)
        self.assertIs(call_kwargs['client_routes_config'], shell.client_routes_config)
        self.assertIsInstance(call_kwargs['load_balancing_policy'], FastTokenAwarePolicy)
        self.assertIs(call_kwargs['ssl_context'], ssl_context)
        mock_ssl_settings.assert_called_once_with('proxy-a.example.com', self.config_file)
        mock_cluster.return_value.connect.assert_called_once_with(self.ks)
        import_task.close()

    def test_validate_columns(self):
        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }
        opts = dict(self.opts)
        opts['skipcols'] = ''
        opts['reportfrequency'] = 1
        opts['ratefile'] = ''
        import_task = ImportTask(shell, self.ks, self.table, self.columns, self.fname, opts, self.protocol_version, self.config_file)
        # Should validate columns successfully
        self.assertTrue(import_task.validate_columns())
        import_task.close()

    def test_import_error_handler_parse_error(self):
        """Test that ImportErrorHandler correctly handles parse errors"""

        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }

        # Create a temp directory for error file
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = dict(self.opts)
            opts['skipcols'] = ''
            opts['reportfrequency'] = 1
            opts['ratefile'] = ''
            opts['errfile'] = os.path.join(tmpdir, 'test_import.err')
            opts['maxparseerrors'] = 10
            opts['maxinserterrors'] = 100

            import_task = ImportTask(shell, self.ks, self.table, self.columns, self.fname, opts, self.protocol_version, self.config_file)
            error_handler = import_task.error_handler

            # Create a parse error
            parse_error = ImportTaskError('ParseError', 'Invalid format', rows=[['val1', 'val2']], attempts=1, final=True)
            self.assertTrue(parse_error.is_parse_error())

            # Handle the parse error
            error_handler.handle_error(parse_error)

            # Verify error counters
            self.assertEqual(error_handler.parse_errors, 1)
            self.assertEqual(error_handler.insert_errors, 0)
            self.assertEqual(error_handler.num_rows_failed, 1)

            # Verify error was not exceeded
            self.assertFalse(error_handler.max_exceeded())

            import_task.close()

    def test_import_error_handler_insert_error(self):
        """Test that ImportErrorHandler correctly handles insert errors"""

        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }

        # Create a temp directory for error file
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = dict(self.opts)
            opts['skipcols'] = ''
            opts['reportfrequency'] = 1
            opts['ratefile'] = ''
            opts['errfile'] = os.path.join(tmpdir, 'test_import.err')
            opts['maxparseerrors'] = 10
            opts['maxinserterrors'] = 100

            import_task = ImportTask(shell, self.ks, self.table, self.columns, self.fname, opts, self.protocol_version, self.config_file)
            error_handler = import_task.error_handler

            # Create an insert error (non-parse error, final)
            insert_error = ImportTaskError('WriteTimeout', 'Timeout occurred', rows=[['val1', 'val2']], attempts=3, final=True)
            self.assertFalse(insert_error.is_parse_error())

            # Handle the insert error
            error_handler.handle_error(insert_error)

            # Verify error counters
            self.assertEqual(error_handler.parse_errors, 0)
            self.assertEqual(error_handler.insert_errors, 1)
            self.assertEqual(error_handler.num_rows_failed, 1)

            # Verify error was not exceeded
            self.assertFalse(error_handler.max_exceeded())

            import_task.close()

    def test_import_error_handler_max_errors_exceeded(self):
        """Test that ImportErrorHandler correctly detects when max errors are exceeded"""

        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }

        # Create a temp directory for error file
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = dict(self.opts)
            opts['skipcols'] = ''
            opts['reportfrequency'] = 1
            opts['ratefile'] = ''
            opts['errfile'] = os.path.join(tmpdir, 'test_import.err')
            opts['maxparseerrors'] = 2
            opts['maxinserterrors'] = 2

            import_task = ImportTask(shell, self.ks, self.table, self.columns, self.fname, opts, self.protocol_version, self.config_file)
            error_handler = import_task.error_handler

            # Ensure the error handler is using the expected error file name
            self.assertTrue(error_handler.err_filename.startswith(opts['errfile']))

            # Add parse errors to exceed limit
            for i in range(3):
                parse_error = ImportTaskError('ParseError', 'Invalid format', rows=[['val1', 'val2']], attempts=1, final=True)
                error_handler.handle_error(parse_error)

            # Verify max errors exceeded
            self.assertTrue(error_handler.max_exceeded())
            self.assertEqual(error_handler.parse_errors, 3)

            import_task.close()

    def test_import_error_handler_retry_errors(self):
        """Test that ImportErrorHandler correctly handles non-final (retry) errors"""

        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }

        # Create a temp directory for error file
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = dict(self.opts)
            opts['skipcols'] = ''
            opts['reportfrequency'] = 1
            opts['ratefile'] = ''
            opts['errfile'] = os.path.join(tmpdir, 'test_import.err')
            opts['maxparseerrors'] = 10
            opts['maxinserterrors'] = 100
            opts['maxattempts'] = 5

            import_task = ImportTask(shell, self.ks, self.table, self.columns, self.fname, opts, self.protocol_version, self.config_file)
            error_handler = import_task.error_handler

            # Create a non-final error (will be retried)
            retry_error = ImportTaskError('WriteTimeout', 'Timeout occurred', rows=[['val1', 'val2']], attempts=2, final=False)

            # Handle the retry error
            error_handler.handle_error(retry_error)

            # Verify error counters - retry errors should not increment insert_errors
            self.assertEqual(error_handler.parse_errors, 0)
            self.assertEqual(error_handler.insert_errors, 0)
            self.assertEqual(error_handler.num_rows_failed, 0)  # Not added to failed rows yet

            import_task.close()

    def test_import_task_error_is_parse_error(self):
        """Test that ImportTaskError correctly identifies parse errors"""

        # Test various parse error types
        parse_error_types = ['ParseError', 'ValueError', 'TypeError', 'IndexError', 'ReadError']
        for error_type in parse_error_types:
            error = ImportTaskError(error_type, 'Error message', rows=[['val1']], attempts=1, final=True)
            self.assertTrue(error.is_parse_error(), f"{error_type} should be classified as a parse error")

        # Test non-parse errors
        non_parse_error_types = ['WriteTimeout', 'WriteFailure', 'Unavailable', 'OperationTimedOut']
        for error_type in non_parse_error_types:
            error = ImportTaskError(error_type, 'Error message', rows=[['val1']], attempts=1, final=True)
            self.assertFalse(error.is_parse_error(), f"{error_type} should NOT be classified as a parse error")

    def test_import_error_handler_error_file_creation(self):
        """Test that error files are created and contain failed rows"""

        shell = self.mock_shell()
        shell.conn.metadata.partitioner = 'Murmur3Partitioner'
        shell.get_ring.return_value = {
            Murmur3Token(-9223372036854775808): self.hosts[0:3],
            Murmur3Token(-4611686018427387904): self.hosts[1:4],
            Murmur3Token(0): [self.hosts[2], self.hosts[3], self.hosts[0]],
            Murmur3Token(4611686018427387904): [self.hosts[3], self.hosts[0], self.hosts[1]]
        }

        # Create a temp directory for error file
        with tempfile.TemporaryDirectory() as tmpdir:
            opts = dict(self.opts)
            opts['skipcols'] = ''
            opts['reportfrequency'] = 1
            opts['ratefile'] = ''
            opts['errfile'] = os.path.join(tmpdir, 'test_import.err')
            opts['maxparseerrors'] = 10
            opts['maxinserterrors'] = 100

            import_task = ImportTask(shell, self.ks, self.table, self.columns, self.fname, opts, self.protocol_version, self.config_file)
            error_handler = import_task.error_handler

            # Handle some errors with specific row data
            error1 = ImportTaskError('ParseError', 'Invalid format', rows=[['row1val1', 'row1val2']], attempts=1, final=True)
            error2 = ImportTaskError('ValueError', 'Bad value', rows=[['row2val1', 'row2val2'], ['row3val1', 'row3val2']], attempts=1, final=True)

            error_handler.handle_error(error1)
            error_handler.handle_error(error2)

            # Verify error file exists
            self.assertTrue(os.path.exists(error_handler.err_filename))

            # Verify filename includes process ID to avoid conflicts in multi-process scenarios
            expected_pattern = f'test_import\\.err\\.pid{os.getpid()}$'
            self.assertRegex(error_handler.err_filename, expected_pattern,
                             f"Error filename should include process ID, got: {error_handler.err_filename}")

            # Read and verify error file contents
            with open(error_handler.err_filename, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 3)  # 3 failed rows total
                self.assertEqual(rows[0], ['row1val1', 'row1val2'])
                self.assertEqual(rows[1], ['row2val1', 'row2val2'])
                self.assertEqual(rows[2], ['row3val1', 'row3val2'])

            import_task.close()


class ScriptedFuture(object):
    """
    Stands in for a driver ResponseFuture, completing as soon as callbacks are attached.
    """

    def __init__(self, error):
        self.error = error

    def add_callbacks(self, callback, callback_args, errback, errback_args):
        if self.error is None:
            callback(None, *callback_args)
        else:
            errback(self.error, *errback_args)


class ScriptedSession(object):
    """
    Stands in for the worker's driver session: requests fail with the given errors, in order,
    and succeed once the errors run out.
    """

    def __init__(self, errors):
        self.errors = list(errors)
        self.executed = []

    def execute_async(self, statement):
        self.executed.append(statement)
        return ScriptedFuture(self.errors.pop(0) if self.errors else None)


def write_timeout():
    return WriteTimeout('Operation timed out - received only 0 responses.',
                        consistency=ConsistencyLevel.ONE, required_responses=1, received_responses=0,
                        write_type=WriteType.UNLOGGED_BATCH)


class TestImportRetries(CopyTaskTest):
    """
    Deterministic replacement for the dtest test_bulk_round_trip_with_timeouts (CASSANDRA-9302),
    which relied on short server timeouts and never saw a retry on fast machines. Here the worker's
    session times out on purpose, so the COPY FROM retry path runs on every machine.
    """

    rows = [['1', 'a'], ['2', 'b'], ['3', 'c']]

    def make_import(self, maxattempts, errors):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.shell = self.mock_shell()
        opts = {'maxattempts': maxattempts, 'errfile': os.path.join(tmpdir.name, 'import.err')}
        import_task = ImportTask(self.shell, self.ks, self.table, self.columns, self.fname, opts,
                                 self.protocol_version, self.config_file)
        self.addCleanup(import_task.close)

        import_process = ImportProcess(import_task.update_params(import_task.make_params(), 0))
        import_process._session = ScriptedSession(errors)
        import_process.outmsg = Mock()
        import_process.make_statement = lambda query, conv, chunk, batch, replicas: (batch['id'], batch['attempts'])
        return import_task, import_process

    def send_chunk(self, import_process):
        """
        Send one chunk as a single batch, the way ImportProcess.inner_run() does.
        """
        chunk = {'id': 1, 'rows': self.rows, 'imported': 0, 'num_rows_sent': len(self.rows)}
        batch = ImportProcess.make_batch(chunk['id'], self.rows)
        replicas = [self.hosts[0]]
        statement = import_process.make_statement(None, None, chunk, batch, replicas)
        future = import_process.session.execute_async(statement)
        future.add_callbacks(callback=import_process.result_callback, callback_args=(batch, chunk),
                             errback=import_process.err_callback, errback_args=(batch, chunk, replicas))
        return chunk

    @staticmethod
    def sent_messages(import_process):
        return [c.args[0] for c in import_process.outmsg.send.call_args_list]

    def handle_errors(self, import_task, messages):
        """
        Pass the worker's errors to the parent's error handler, as ImportTask.receive_results() does.
        """
        for msg in messages:
            if isinstance(msg, ImportTaskError):
                import_task.error_handler.handle_error(msg)
        return [c.args[0] for c in self.shell.printerr.call_args_list]

    def test_retries_timeouts_until_the_batch_is_imported(self):
        import_task, import_process = self.make_import(maxattempts=3,
                                                       errors=[write_timeout(), OperationTimedOut('client timeout')])
        chunk = self.send_chunk(import_process)

        self.assertEqual(import_process.session.executed, [(1, 1), (1, 2), (1, 3)])
        errors, results = self.sent_messages(import_process)[:2], self.sent_messages(import_process)[2:]
        self.assertEqual([(e.name, e.attempts, e.final) for e in errors],
                         [('WriteTimeout', 1, False), ('OperationTimedOut', 2, False)])
        self.assertEqual([type(r) for r in results], [ImportProcessResult])
        self.assertEqual(results[0].imported, len(self.rows))
        self.assertEqual(chunk['imported'], len(self.rows))

        printed = self.handle_errors(import_task, errors)
        self.assertEqual(len(printed), 2)
        self.assertIn('will retry later, attempt 1 of 3', printed[0])
        self.assertIn('will retry later, attempt 2 of 3', printed[1])
        self.assertEqual(import_task.error_handler.insert_errors, 0)
        self.assertEqual(import_task.error_handler.num_rows_failed, 0)

    def test_gives_up_when_every_attempt_times_out(self):
        import_task, import_process = self.make_import(maxattempts=3, errors=[write_timeout()] * 3)
        chunk = self.send_chunk(import_process)

        self.assertEqual(import_process.session.executed, [(1, 1), (1, 2), (1, 3)])
        messages = self.sent_messages(import_process)
        errors = [m for m in messages if isinstance(m, ImportTaskError)]
        self.assertEqual([(e.name, e.attempts, e.final) for e in errors],
                         [('WriteTimeout', 1, False), ('WriteTimeout', 2, False), ('WriteTimeout', 3, True)])
        # the chunk is still accounted for, so the parent does not wait for it forever
        self.assertIsInstance(messages[-1], ImportProcessResult)
        self.assertEqual(chunk['imported'], len(self.rows))

        printed = self.handle_errors(import_task, errors)
        self.assertIn('will retry later, attempt 2 of 3', printed[1])
        self.assertIn('given up after 3 attempts', printed[2])
        self.assertEqual(import_task.error_handler.insert_errors, len(self.rows))
        with open(import_task.error_handler.err_filename) as f:
            self.assertEqual(list(csv.reader(f)), self.rows)

    def test_ignores_a_late_client_timeout_for_an_imported_chunk(self):
        # the driver can report a client timeout for rows already written (PYTHON-652)
        _, import_process = self.make_import(maxattempts=3, errors=[])
        chunk = self.send_chunk(import_process)
        import_process.outmsg.reset_mock()

        batch = ImportProcess.make_batch(chunk['id'], self.rows)
        import_process.err_callback(OperationTimedOut('late timeout'), batch, chunk, [self.hosts[0]])

        self.assertEqual(len(import_process.session.executed), 1)
        import_process.outmsg.send.assert_not_called()


class TestExpBackoffRetryPolicy(unittest.TestCase):
    """
    COPY TO retries server read timeouts through this policy, backing off between attempts.
    """

    def setUp(self):
        self.policy = ExpBackoffRetryPolicy(Mock(max_attempts=3))

    def test_retries_timeouts_with_backoff_up_to_max_attempts(self):
        decisions = []
        with patch('cqlshlib.copyutil.randint', side_effect=lambda low, high: high) as mock_randint, \
                patch('cqlshlib.copyutil.time.sleep') as mock_sleep:
            for retry_num in range(4):
                decisions.append(self.policy.on_read_timeout(None, ConsistencyLevel.ONE, 1, 0, False, retry_num))

        self.assertEqual(decisions, [(RetryPolicy.RETRY, ConsistencyLevel.ONE)] * 3 + [(RetryPolicy.RETHROW, None)])
        # the delay is drawn from [0, 2^(retry_num + 1) - 1] seconds
        self.assertEqual([c.args for c in mock_randint.call_args_list], [(0, 1), (0, 3), (0, 7)])
        self.assertEqual([c.args for c in mock_sleep.call_args_list], [(1,), (3,), (7,)])

    def test_retries_immediately_on_a_zero_delay(self):
        with patch('cqlshlib.copyutil.randint', return_value=0), \
                patch('cqlshlib.copyutil.time.sleep') as mock_sleep:
            decision = self.policy.on_write_timeout(None, ConsistencyLevel.ONE, 'SIMPLE', 1, 0, 0)

        self.assertEqual(decision, (RetryPolicy.RETRY, ConsistencyLevel.ONE))
        mock_sleep.assert_not_called()
