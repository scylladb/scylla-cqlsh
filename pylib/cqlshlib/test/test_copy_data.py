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

from .basecase import BaseTestCase
from .cassconnect import create_keyspace, get_cassandra_connection, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test


class CopyTestCase(BaseTestCase):
    """
    Base class for the COPY tests ported from the dtest cqlsh_copy_tests.py: every class gets its own
    keyspace, and every test its own temp dir for the CSV files and the COPY FROM error files.
    """

    @classmethod
    def setUpClass(cls):
        cls.cluster = get_cassandra_connection()
        cls.session = cls.cluster.connect()
        cls.session.default_timeout = 60.0
        cls.ks = create_keyspace(cls.session)

    @classmethod
    def tearDownClass(cls):
        cls.cluster.shutdown()
        remove_db()

    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmpdir = tmpdir.name

    def create_table(self, name, columns):
        """
        Create a table in the class keyspace, dropping any table of the same name left by another test,
        and return its qualified name.
        """
        table = '%s.%s' % (self.ks, name)
        self.session.execute('DROP TABLE IF EXISTS %s' % (table,))
        self.session.execute('CREATE TABLE %s (%s)' % (table, columns))
        return table

    def csv_file(self, name):
        return os.path.join(self.tmpdir, name)

    def write_csv(self, name, rows):
        fname = self.csv_file(name)
        with open(fname, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(rows)
        return fname

    def run_cqlsh(self, cmds):
        """
        Run cqlsh commands and return the output. The exit status is not checked: cqlsh exits non zero
        whenever it prints an error, so the tests check the output and the data instead.
        """
        # pass our environment on, so cqlsh runs with the same PATH and interpreter as the tests
        output, _ = call_cqlsh_for_test(input=cmds + '\n', env=os.environ.copy())
        return output

    def copy_from(self, table, fname, options=''):
        """
        Run COPY FROM, keeping the file of rejected rows in the temp dir rather than the working directory.
        """
        errfile = self.csv_file('import.err')
        with_clause = "ERRFILE = '%s'" % (errfile,)
        if options:
            with_clause += ' AND ' + options
        return self.run_cqlsh("COPY %s FROM '%s' WITH %s;" % (table, fname, with_clause))

    def select_all(self, table):
        return sorted(tuple(row) for row in self.session.execute('SELECT * FROM %s' % (table,)))


class TestCopyFromValidation(CopyTestCase):
    """
    COPY FROM must reject CSV values that do not match the column types, and import the ones that do.
    """

    def validate_on_read(self, load_as_int, expect_invalid):
        table = self.create_table('testvalidate', 'a int PRIMARY KEY, b int')
        fname = self.write_csv('data.csv', [[1, load_as_int]])

        output = self.copy_from('%s (a, b)' % (table,), fname)
        rows = self.select_all(table)
        if expect_invalid:
            self.assertIn('Failed to import', output)
            self.assertEqual(rows, [])
        else:
            self.assertNotIn('Failed to import', output)
            self.assertIn('1 rows imported from 1 files', output)
            self.assertEqual(rows, [(1, load_as_int)])

    def test_read_valid_data(self):
        self.validate_on_read(2, expect_invalid=False)
