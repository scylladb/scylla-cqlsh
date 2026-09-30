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
import json
import os
import tempfile

from cassandra.concurrent import execute_concurrent_with_args
from cassandra.metadata import MAX_LONG

from .basecase import BaseTestCase
from .cassconnect import create_keyspace, get_cassandra_connection, get_keyspace, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test


class TestCopyRoundTripWithRetries(BaseTestCase):
    """
    Replaces the dtest test_bulk_round_trip_with_timeouts (CASSANDRA-9302), which set short server
    timeouts and hoped COPY would retry; on fast machines it never did. Here the failures are injected
    through CQLSH_COPY_TEST_FAILURES, so COPY TO and COPY FROM retry on every run, and the round trip
    must still export and import every row.
    """

    num_rows = 1000
    max_attempts = 3
    export_max_attempts = 5

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
        output, _ = call_cqlsh_for_test(input=cmd + ';\n', env=env)
        return output

    def csv_file(self, name):
        return os.path.join(self.tmpdir, name)

    def read_csv(self, fname):
        with open(fname, newline='') as f:
            return sorted(csv.reader(f))

    def count_rows(self):
        return self.session.execute('SELECT COUNT(*) FROM %s' % (self.table,)).one()[0]

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
