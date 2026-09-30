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

from cassandra.concurrent import execute_concurrent_with_args

from .basecase import BaseTestCase
from .cassconnect import create_keyspace, get_cassandra_connection, get_keyspace, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test


class TestCopyOptions(BaseTestCase):
    """
    Checks the options of COPY TO and COPY FROM, ported from the dtest cqlsh_copy_tests.py.
    Each test creates its own table in a keyspace shared by the class.
    """

    @classmethod
    def setUpClass(cls):
        cls.cluster = get_cassandra_connection()
        cls.session = cls.cluster.connect()
        cls.session.default_timeout = 60.0
        create_keyspace(cls.session)
        cls.ks = get_keyspace()

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()
        remove_db()

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = tmpdir.name

    def run_cqlsh(self, cmd):
        """
        Run a command and return its output. The exit status is not checked: cqlsh exits with 2
        whenever it prints an error, so the tests check the output and the data instead.
        """
        env = os.environ.copy()
        output, _ = call_cqlsh_for_test(input=cmd + ';\n', env=env)
        return output

    def copy_to(self, table, fname, options=''):
        cmd = "COPY %s.%s TO '%s'" % (self.ks, table, fname)
        if options:
            cmd += ' WITH ' + options
        return self.run_cqlsh(cmd)

    def csv_file(self, name):
        return os.path.join(self.tmpdir, name)

    def read_csv(self, fname, **fmtparams):
        with open(fname, newline='', encoding='utf-8') as f:
            return list(csv.reader(f, **fmtparams))

    def create_table(self, table, columns):
        self.session.execute('CREATE TABLE %s.%s (%s)' % (self.ks, table, columns))

    def insert_rows(self, table, columns, rows):
        insert = self.session.prepare('INSERT INTO %s.%s (%s) VALUES (%s)'
                                      % (self.ks, table, ', '.join(columns), ', '.join('?' * len(columns))))
        execute_concurrent_with_args(self.session, insert, rows)

    def check_delimiter(self, table, delimiter):
        """
        Export a table with COPY TO WITH DELIMITER and check that the CSV file splits on that delimiter.
        """
        self.create_table(table, 'a int PRIMARY KEY, b int')
        rows = [(i, i * 10) for i in range(1000)]
        self.insert_rows(table, ('a', 'b'), rows)

        fname = self.csv_file('exported.csv')
        output = self.copy_to(table, fname, "DELIMITER = '%s'" % (delimiter,))
        self.assertIn('1000 rows exported', output)
        self.assertEqual(sorted(self.read_csv(fname, delimiter=delimiter)),
                         sorted([str(a), str(b)] for a, b in rows))
        return fname

    def test_colon_delimiter(self):
        self.check_delimiter('testdelimiter_colon', ':')

    def test_letter_delimiter(self):
        self.check_delimiter('testdelimiter_letter', 'a')

    def test_number_delimiter(self):
        fname = self.check_delimiter('testdelimiter_number', '1')
        # values that contain the delimiter are quoted
        with open(fname, encoding='utf-8') as f:
            lines = f.read().splitlines()
        self.assertIn('"1"1"10"', lines)
        self.assertIn('2120', lines)
