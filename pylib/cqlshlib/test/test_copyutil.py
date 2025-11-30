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
from unittest.mock import Mock

from cassandra.metadata import MIN_LONG, Murmur3Token

from cqlshlib.copyutil import ExportTask, ImportTask, ImportTaskError


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
        shell.get_column_names.return_value = self.columns
        shell.debug = False
        shell.coverage = False
        shell.coveragerc_path = None
        shell.port = 9042
        shell.ssl = None
        shell.auth_provider = None
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


class TestImportTask(CopyTaskTest):
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
            expected_pattern = rf'test_import\.err\.pid{os.getpid()}$'
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

