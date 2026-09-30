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
import datetime
import os
import random
import tempfile
from collections import namedtuple
from decimal import Decimal
from uuid import UUID, uuid4

from cassandra.concurrent import execute_concurrent_with_args

from .basecase import BaseTestCase, cqlsh_env_in_utc
from .cassconnect import create_keyspace, get_cassandra_connection, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test


class HashableDict(dict):
    """
    A dict that can be the key of another dict, to insert a map whose keys are maps.
    """

    def __hash__(self):
        return hash(frozenset(self.items()))


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
        # pass our environment on, so cqlsh runs with the same PATH and interpreter as the tests,
        # with timestamps printed in UTC
        output, _ = call_cqlsh_for_test(input=cmds + '\n', env=cqlsh_env_in_utc())
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

    def read_csv(self, fname):
        with open(fname, newline='', encoding='utf-8') as f:
            return list(csv.reader(f))

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

    def test_read_invalid_float(self):
        self.validate_on_read(2.14, expect_invalid=True)

    def test_read_invalid_uuid(self):
        self.validate_on_read(uuid4(), expect_invalid=True)

    def test_read_invalid_text(self):
        self.validate_on_read('test', expect_invalid=True)

    def test_wrong_number_of_columns(self):
        table = self.create_table('testcolumns', 'a int PRIMARY KEY, b int')
        fname = self.write_csv('data.csv', [[1, 2, 3]])

        output = self.copy_from(table, fname)
        self.assertIn('Failed to import 1 rows', output)
        self.assertIn('Invalid row length 3 should be 2', output)
        self.assertEqual(self.select_all(table), [])


class TestCopyAllDatatypes(CopyTestCase):
    """
    COPY on a table with a column of every CQL type, including nested collections and UDTs (CASSANDRA-9302).
    """

    columns = 'abcdefghijklmnopqrstuvw'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.session.execute('CREATE TYPE %s.name_type (firstname text, lastname text)' % (cls.ks,))
        cls.session.execute('CREATE TYPE %s.address_type (name frozen<name_type>, number int, street text, '
                            'phones set<text>)' % (cls.ks,))
        cls.session.execute("""
            CREATE TABLE %s.testdatatype (
                a ascii PRIMARY KEY,
                b bigint,
                c blob,
                d boolean,
                e decimal,
                f double,
                g float,
                h inet,
                i int,
                j text,
                k timestamp,
                l timeuuid,
                m uuid,
                n varchar,
                o varint,
                p list<int>,
                q set<text>,
                r map<timestamp, text>,
                s tuple<int, text, boolean>,
                t frozen<address_type>,
                u frozen<list<list<address_type>>>,
                v frozen<map<map<int,int>,set<text>>>,
                w frozen<set<set<inet>>>
            )""" % (cls.ks,))
        cls.table = '%s.testdatatype' % (cls.ks,)

        date1 = datetime.datetime(2005, 7, 14, 12, 30)
        date2 = datetime.datetime(2005, 7, 14, 13, 30)
        # the driver serializes a UDT from any object with its field names as attributes
        Name = namedtuple('Name', ('firstname', 'lastname'))
        Address = namedtuple('Address', ('name', 'number', 'street', 'phones'))
        addr1 = Address(Name('name1', 'last1'), 1, 'street 1', {'1111 2222', '3333 4444'})
        addr2 = Address(Name('name2', 'last2'), 2, 'street 2', {'5555 6666', '7777 8888'})
        addr3 = Address(Name('name3', 'last3'), 3, 'street 3', {'1111 2222', '3333 4444'})
        addr4 = Address(Name('name4', 'last4'), 4, 'street 4', {'5555 6666', '7777 8888'})
        cls.data = (
            'ascii',  # a ascii
            2 ** 40,  # b bigint
            bytes.fromhex('beef'),  # c blob
            True,  # d boolean
            Decimal('3.14'),  # e decimal
            2.444,  # f double
            1.1,  # g float
            '127.0.0.1',  # h inet
            25,  # i int
            'ヽ(`ー`)/',  # j text
            date1,  # k timestamp
            UUID('0b8d9b4e-f4a2-11e5-9ce9-5e5517507c66'),  # l timeuuid
            UUID('4ce4b0b5-9e0a-4a4f-a9c1-e1a3d0a8f6f2'),  # m uuid
            'asdf',  # n varchar
            2 ** 65,  # o varint
            [1, 2, 3],  # p list<int>
            {'3', '2', '1'},  # q set<text>
            {date1: '1', date2: '2'},  # r map<timestamp, text>
            (1, '1', True),  # s tuple<int, text, boolean>
            addr1,  # t frozen<address_type>
            [[addr1, addr2], [addr3, addr4]],  # u frozen<list<list<address_type>>>
            {HashableDict({1: 1, 2: 2}): {'1', '2', '3'}},  # v frozen<map<map<int,int>,set<text>>>
            {frozenset({'127.0.0.1'}), frozenset({'127.0.0.1', '127.0.0.2'})},  # w frozen<set<set<inet>>>
        )

    # cls.data as COPY TO writes it, with the default COPY options
    addresses_csv = [
        "{name: {firstname: 'name%d', lastname: 'last%d'}, number: %d, street: 'street %d', phones: {%s}}"
        % (i, i, i, i, phones)
        for i, phones in ((1, "'1111 2222', '3333 4444'"), (2, "'5555 6666', '7777 8888'"),
                          (3, "'1111 2222', '3333 4444'"), (4, "'5555 6666', '7777 8888'"))
    ]
    data_csv = [
        'ascii',
        '1099511627776',
        '0xbeef',
        'True',
        '3.14',
        '2.444',
        '1.1',
        '127.0.0.1',
        '25',
        'ヽ(`ー`)/',
        '2005-07-14 12:30:00.000+0000',
        '0b8d9b4e-f4a2-11e5-9ce9-5e5517507c66',
        '4ce4b0b5-9e0a-4a4f-a9c1-e1a3d0a8f6f2',
        'asdf',
        '36893488147419103232',
        '[1, 2, 3]',
        "{'1', '2', '3'}",
        "{'2005-07-14 12:30:00.000+0000': '1', '2005-07-14 13:30:00.000+0000': '2'}",
        "(1, '1', True)",
        addresses_csv[0],
        '[[%s, %s], [%s, %s]]' % tuple(addresses_csv),
        "{{1: 1, 2: 2}: {'1', '2', '3'}}",
        "{{'127.0.0.1'}, {'127.0.0.1', '127.0.0.2'}}",
    ]

    def setUp(self):
        super().setUp()
        self.session.execute('TRUNCATE %s' % (self.table,))

    def insert_data(self):
        insert = self.session.prepare('INSERT INTO %s (%s) VALUES (%s)'
                                      % (self.table, ', '.join(self.columns), ', '.join('?' * len(self.columns))))
        self.session.execute(insert, self.data)

    def test_all_datatypes_round_trip(self):
        self.insert_data()
        exported_rows = self.select_all(self.table)

        fname = self.csv_file('exported.csv')
        output = self.run_cqlsh("COPY %s TO '%s';" % (self.table, fname))
        self.assertIn('1 rows exported to 1 files', output)

        self.session.execute('TRUNCATE %s' % (self.table,))
        output = self.copy_from(self.table, fname)
        self.assertIn('1 rows imported from 1 files', output)
        self.assertEqual(self.select_all(self.table), exported_rows)

    def test_all_datatypes_write(self):
        self.insert_data()

        fname = self.csv_file('exported.csv')
        output = self.run_cqlsh("COPY %s TO '%s';" % (self.table, fname))
        self.assertIn('1 rows exported to 1 files', output)
        self.assertEqual(self.read_csv(fname), [self.data_csv])

    def test_all_datatypes_read(self):
        # the rows the driver writes for cls.data are the ones COPY FROM must write for its CSV
        self.insert_data()
        expected_rows = self.select_all(self.table)
        self.session.execute('TRUNCATE %s' % (self.table,))

        fname = self.write_csv('data.csv', [self.data_csv])
        output = self.copy_from(self.table, fname)
        self.assertIn('1 rows imported from 1 files', output)
        self.assertEqual(self.select_all(self.table), expected_rows)


class TestCopyToCollections(CopyTestCase):
    """
    COPY TO must write each row of a collection column in the CQL literal format cqlsh prints.
    """

    num_rows = 1000

    def random_uuids(self, rng, n):
        return [UUID(int=rng.getrandbits(128), version=4) for _ in range(n)]

    def export_sorted(self, table):
        fname = self.csv_file('exported.csv')
        output = self.run_cqlsh("COPY %s TO '%s';" % (table, fname))
        self.assertIn('%d rows exported to 1 files' % (self.num_rows,), output)
        return sorted(self.read_csv(fname), key=lambda row: int(row[0]))

    def test_list_data(self):
        table = self.create_table('testlist', 'a int PRIMARY KEY, b list<uuid>')
        rng = random.Random(0)
        args = [(i, self.random_uuids(rng, rng.randint(1, 5))) for i in range(self.num_rows)]
        insert = self.session.prepare('INSERT INTO %s (a, b) VALUES (?, ?)' % (table,))
        execute_concurrent_with_args(self.session, insert, args)

        expected = [[str(a), '[%s]' % (', '.join(str(u) for u in b),)] for a, b in args]
        self.assertEqual(self.export_sorted(table), expected)
