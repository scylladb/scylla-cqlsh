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

import bisect
import csv
import json
import os
import re
import subprocess
import tempfile

from cassandra.concurrent import execute_concurrent_with_args
from cassandra.metadata import MAX_LONG

from .basecase import BaseTestCase
from .cassconnect import create_keyspace, get_cassandra_connection, get_keyspace, remove_db
from .run_cqlsh import CqlshRunner


class CopyTestCase(BaseTestCase):
    """
    Creates a keyspace per class with a simple table that every test fills with num_rows rows, and runs
    COPY commands with failures injected through CQLSH_COPY_TEST_FAILURES.
    """

    num_rows = 1000
    # a COPY that hangs, for example waiting on a dead child process, fails the test instead of blocking the suite
    copy_timeout = 300

    @classmethod
    def setUpClass(cls):
        cls.cluster = get_cassandra_connection()
        cls.session = cls.cluster.connect()
        cls.session.default_timeout = 60.0
        create_keyspace(cls.session)
        cls.table = '%s.bulk' % (get_keyspace(),)
        cls.session.execute('CREATE TABLE %s (k int PRIMARY KEY, v text)' % (cls.table,))

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()
        remove_db()

    def setUp(self):
        self.session.execute('TRUNCATE %s' % (self.table,))
        insert = self.session.prepare('INSERT INTO %s (k, v) VALUES (?, ?)' % (self.table,))
        execute_concurrent_with_args(self.session, insert, [(i, 'value %d' % (i,)) for i in range(self.num_rows)])

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = tmpdir.name

    def run_copy(self, cmd, failures):
        """
        Run a COPY command and return its output. The exit status is not checked: every error cqlsh
        prints, retried or not, makes it non zero, so the tests check the output and the data instead.
        """
        env = os.environ.copy()
        env['CQLSH_COPY_TEST_FAILURES'] = json.dumps(failures)
        runner = CqlshRunner(keyspace=get_keyspace(), prompt=None, tty=False, env=env)
        try:
            output, _ = runner.proc.communicate((cmd + ';\n').encode('utf-8'), timeout=self.copy_timeout)
        except subprocess.TimeoutExpired:
            runner.proc.kill()
            runner.proc.communicate()
            self.fail('%s did not finish in %d seconds' % (cmd, self.copy_timeout))
        return output.decode('utf-8')

    def csv_file(self, name):
        return os.path.join(self.tmpdir, name)

    def read_csv(self, fname):
        with open(fname, newline='') as f:
            return sorted(csv.reader(f))

    def count_rows(self):
        return self.session.execute('SELECT COUNT(*) FROM %s' % (self.table,)).one()[0]


class TestCopyRoundTripWithRetries(CopyTestCase):
    """
    Replaces the dtest test_bulk_round_trip_with_timeouts (CASSANDRA-9302), which set short server
    timeouts and hoped COPY would retry; on fast machines it never did. Here the failures are injected
    through CQLSH_COPY_TEST_FAILURES, so COPY TO and COPY FROM retry on every run, and the round trip
    must still export and import every row.
    """

    max_attempts = 3
    export_max_attempts = 5

    def copy_to_with_retries(self, fname):
        # The token ranges in the upper half of the ring fail before being exported. A worker usually
        # sees attempt numbers from 1 and fails on attempts 1 and 2, but ExportTask.send_work() counts
        # the attempt after queuing the range, so a worker can also see 0 and fail a third time.
        # MAXATTEMPTS leaves room for that, so no range is given up.
        failures = {'failing_range': {'start': 0, 'end': MAX_LONG, 'num_failures': 3}}
        output = self.run_copy("COPY %s TO '%s' WITH MAXATTEMPTS = %d"
                               % (self.table, fname, self.export_max_attempts), failures)
        self.assertIn('will try again later attempt 1 of %d' % (self.export_max_attempts,), output)
        self.assertIn('will try again later attempt 2 of %d' % (self.export_max_attempts,), output)
        self.assertNotIn('permanently given up', output)
        return output

    def copy_from(self, fname, failures_for_batch_30):
        # a CHUNKSIZE of 10 splits the rows into 100 batches, so the injected failures hit only one of them
        failures = {'failing_batch': {'id': 30, 'failures': failures_for_batch_30}}
        return self.run_copy("COPY %s FROM '%s' WITH CHUNKSIZE = 10 AND MAXATTEMPTS = %d AND ERRFILE = '%s'"
                             % (self.table, fname, self.max_attempts, self.csv_file('import.err')), failures)

    def test_bulk_round_trip_with_retries(self):
        exported = self.csv_file('exported.csv')
        self.copy_to_with_retries(exported)
        rows = self.read_csv(exported)
        self.assertEqual(len(rows), self.num_rows)

        self.session.execute('TRUNCATE %s' % (self.table,))
        # fails on attempts 1 and 2 and succeeds on the last attempt
        output = self.copy_from(exported, failures_for_batch_30=self.max_attempts)
        self.assertIn('will retry later, attempt 1 of %d' % (self.max_attempts,), output)
        self.assertIn('will retry later, attempt 2 of %d' % (self.max_attempts,), output)
        self.assertNotIn('given up', output)
        self.assertEqual(self.count_rows(), self.num_rows)

        reexported = self.csv_file('reexported.csv')
        self.copy_to_with_retries(reexported)
        self.assertEqual(self.read_csv(reexported), rows)

    def test_copy_from_gives_up_after_max_attempts(self):
        exported = self.csv_file('exported.csv')
        self.run_copy("COPY %s TO '%s'" % (self.table, exported), {})
        self.session.execute('TRUNCATE %s' % (self.table,))

        output = self.copy_from(exported, failures_for_batch_30=self.max_attempts + 1)
        self.assertIn('will retry later, attempt %d of %d' % (self.max_attempts - 1, self.max_attempts), output)
        self.assertIn('given up after %d attempts' % (self.max_attempts,), output)
        # only the rows of the failing batch are missing
        self.assertEqual(self.count_rows(), self.num_rows - 10)


class TestCopyToWithFailures(CopyTestCase):
    """
    Ported from the dtest COPY TO failure injection tests (CASSANDRA-9304). The worker processes run the
    export query of a failing range against a table that does not exist, or exit on an exit range.
    """

    def ring_range_with_rows(self):
        """
        Return a (start, end] range of the ring that holds at least one row. cqlsh never injects failures
        in the first and the last range of the ring, whose start or end token is None, so skip those.
        """
        tokens = sorted(t.value for t in self.cluster.metadata.token_map.ring)
        for row in self.session.execute('SELECT token(k) FROM %s' % (self.table,)):
            i = bisect.bisect_left(tokens, row[0])
            if 0 < i < len(tokens) and tokens[i - 1] != 0:
                return tokens[i - 1], tokens[i]
        self.fail('no row in the inner ranges of the ring %s' % (tokens,))

    def count_rows_in_range(self, start, end):
        return self.session.execute('SELECT COUNT(*) FROM %s WHERE token(k) > %d AND token(k) <= %d'
                                    % (self.table, start, end)).one()[0]

    def test_copy_to_with_more_failures_than_max_attempts(self):
        start, end = self.ring_range_with_rows()
        exported = self.csv_file('exported.csv')
        # the range fails on the three attempts COPY TO makes, so it gives up on it
        failures = {'failing_range': {'start': start, 'end': end, 'num_failures': 5}}
        output = self.run_copy("COPY %s TO '%s' WITH MAXATTEMPTS = 3" % (self.table, exported), failures)
        self.assertIn('will try again later attempt 2 of 3', output)
        self.assertIn('permanently given up after 0 rows and 3 attempts', output)
        self.assertIn('some records might be missing', output)
        # only the rows of the failing range are missing
        self.assertEqual(len(self.read_csv(exported)), self.num_rows - self.count_rows_in_range(start, end))

    def test_copy_to_with_fewer_failures_than_max_attempts(self):
        start, end = self.ring_range_with_rows()
        exported = self.csv_file('exported.csv')
        # the worker fails while the attempt number it sees is below num_failures, so the range fails on
        # attempts 1 and 2 and is exported on attempt 3 out of 5; ExportTask.send_work() counts the attempt
        # after queuing the range, so a worker can also see 0 and fail once more, which still fits in 5
        failures = {'failing_range': {'start': start, 'end': end, 'num_failures': 3}}
        output = self.run_copy("COPY %s TO '%s' WITH MAXATTEMPTS = 5" % (self.table, exported), failures)
        self.assertIn('will try again later attempt 2 of 5', output)
        self.assertNotIn('permanently given up', output)
        self.assertNotIn('some records might be missing', output)
        self.assertEqual(len(self.read_csv(exported)), self.num_rows)

    def test_copy_to_with_child_process_crashing(self):
        start, end = self.ring_range_with_rows()
        exported = self.csv_file('exported.csv')
        # the worker that gets the range exits, so COPY TO stops without the rows of that range
        failures = {'exit_range': {'start': start, 'end': end}}
        output = self.run_copy("COPY %s TO '%s'" % (self.table, exported), failures)
        self.assertRegex(output, r'Child process \d+ died with exit code 1')
        self.assertIn('some records might be missing', output)
        # other ranges may be lost with the worker too, so only an upper bound is deterministic
        self.assertLessEqual(len(self.read_csv(exported)), self.num_rows - self.count_rows_in_range(start, end))


class TestCopyFromWithFailures(CopyTestCase):
    """
    Ported from the dtest COPY FROM failure injection tests (CASSANDRA-9302). The worker processes send
    a failing batch to a table that does not exist, or exit on an exit batch. With a CHUNKSIZE of 1 every
    chunk, and so every batch, holds one row, and batch n holds the n-th row of the csv file.
    """

    failing_batch_id = 30

    def setUp(self):
        super().setUp()
        self.exported = self.csv_file('exported.csv')
        self.run_copy("COPY %s TO '%s'" % (self.table, self.exported), {})
        with open(self.exported, newline='') as f:
            self.failing_row = list(csv.reader(f))[self.failing_batch_id - 1]
        self.session.execute('TRUNCATE %s' % (self.table,))

    def copy_from(self, failures, options=''):
        self.errfile = self.csv_file('import.err')
        return self.run_copy("COPY %s FROM '%s' WITH CHUNKSIZE = 1 AND ERRFILE = '%s'%s"
                             % (self.table, self.exported, self.errfile, options), failures)

    def row_exists(self, row):
        return self.session.execute('SELECT * FROM %s WHERE k = %s' % (self.table, row[0])).one() is not None

    def test_copy_from_with_more_failures_than_max_attempts(self):
        # the batch fails on the three attempts COPY FROM makes, so it gives up on it
        failures = {'failing_batch': {'id': self.failing_batch_id, 'failures': 5}}
        output = self.copy_from(failures, ' AND MAXATTEMPTS = 3')
        self.assertIn('will retry later, attempt 2 of 3', output)
        self.assertIn('given up after 3 attempts', output)
        # cqlsh appends the pid of the cqlsh process to the name of the error file
        written_to = re.search(r'Failed to process 1 rows; failed rows written to (%s\.pid\d+)'
                               % (re.escape(self.errfile),), output)
        self.assertIsNotNone(written_to, output)
        self.assertEqual(self.read_csv(written_to.group(1)), [self.failing_row])
        self.assertEqual(self.count_rows(), self.num_rows - 1)
        self.assertFalse(self.row_exists(self.failing_row))

    def test_copy_from_with_fewer_failures_than_max_attempts(self):
        # batches start at attempt 1 and fail while the attempt is below failures,
        # so the batch fails on attempts 1 and 2 and is imported on attempt 3 out of 5
        failures = {'failing_batch': {'id': self.failing_batch_id, 'failures': 3}}
        output = self.copy_from(failures, ' AND MAXATTEMPTS = 5')
        self.assertIn('Failed to import 1 rows', output)
        self.assertIn('will retry later, attempt 2 of 5', output)
        self.assertNotIn('attempt 3 of 5', output)
        self.assertNotIn('given up', output)
        self.assertNotIn('Failed to process', output)
        self.assertEqual(self.count_rows(), self.num_rows)
        self.assertTrue(self.row_exists(self.failing_row))
