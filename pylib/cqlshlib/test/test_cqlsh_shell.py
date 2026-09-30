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

import datetime
import os
import re

from cassandra.concurrent import execute_concurrent_with_args
from cassandra.util import Date, Time

from .basecase import BaseTestCase, dedent
from .cassconnect import create_keyspace, get_cassandra_connection, get_keyspace, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test
from .cassconnect import testrun_cqlsh as run_cqlsh_for_test


class TestCqlshShell(BaseTestCase):
    """
    cqlsh shell behavior ported from the dtest cqlsh_tests: how values are printed, and how
    shell commands such as TRACING, SOURCE and DESCRIBE behave.
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
        env = os.environ.copy()
        # without TZ, cqlsh prints timestamps in UTC
        env.pop('TZ', None)
        env['LC_CTYPE'] = 'en_US.utf8'
        self.env = env

    def run_cqlsh(self, cmds, args=()):
        """
        Run cqlsh on a pipe and return its output, with stderr merged in. The exit status is not
        checked: cqlsh exits non zero whenever it prints an error, so the tests check the output.
        """
        output, _ = call_cqlsh_for_test(input=cmds, env=self.env, args=args)
        return output

    def select_rows(self, query):
        """
        Run a SELECT through cqlsh and return the printed rows, each one a list of its cells with
        the padding stripped, so the tests do not depend on the column widths.
        """
        output = self.run_cqlsh(query)
        lines = output.splitlines()
        rules = [i for i, line in enumerate(lines) if re.match(r'^-+(\+-+)*$', line)]
        self.assertTrue(rules, msg='no result table in the cqlsh output:\n%s' % (output,))
        rows = []
        for line in lines[rules[0] + 1:]:
            if not line.strip():
                break
            rows.append([cell.strip() for cell in line.split('|')])
        return rows

    def test_past_and_future_dates(self):
        self.run_cqlsh("""
            CREATE TABLE simpledate (id int PRIMARY KEY, value timestamp);
            INSERT INTO simpledate (id, value) VALUES (1, '2143-04-19 11:21:01+0000');
            INSERT INTO simpledate (id, value) VALUES (2, '1943-04-19 11:21:01+0000');
            """)
        rows = dict(self.session.execute('SELECT id, value FROM %s.simpledate' % (self.ks,)))
        self.assertEqual(rows, {1: datetime.datetime(2143, 4, 19, 11, 21, 1),
                                2: datetime.datetime(1943, 4, 19, 11, 21, 1)})

        output = self.run_cqlsh('SELECT * FROM simpledate;')
        self.assertIn('2143-04-19 11:21:01.000000+0000', output)
        self.assertIn('1943-04-19 11:21:01.000000+0000', output)

    def test_float_formatting(self):  # CASSANDRA-9224
        # (inserted literal, printed double, printed float); test_numeric_output covers whole numbers,
        # these cover the switch to exponent notation and rounding to 5 significant digits
        values = [
            ('0.00000006', '6e-08', '6e-08'),
            ('0.00006', '6e-05', '6e-05'),
            ('0.0006', '0.0006', '0.0006'),
            ('0.6', '0.6', '0.6'),
            ('6.000000', '6', '6'),
            ('6.1234', '6.1234', '6.1234'),
            ('6.123454', '6.12345', '6.12345'),
            # the float is stored as 6.12345504..., so it rounds up and the double does not
            ('6.123455', '6.12345', '6.12346'),
            ('6.12345555555555', '6.12346', '6.12346'),
            ('1116.12345', '1116.12345', '1116.12341'),
            ('11116.12345', '11116.12345', '11116.12305'),
            ('111116.12345', '1.1112e+05', '1.1112e+05'),
            ('11111116.12345', '1.1111e+07', '1.1111e+07'),
        ]
        rows = [('+', literal, printed_double, printed_float) for literal, printed_double, printed_float in values]
        rows += [('-', '-' + literal, '-' + printed_double, '-' + printed_float)
                 for literal, printed_double, printed_float in values]
        rows += [('0', literal, printed, printed) for literal, printed in (
            ('0', '0'), ('0.000000000001', '1e-12'), ('0.000000000000001', '1e-15'),
            ('0.0000000000000001', '1e-16'))]

        self.session.execute('CREATE TABLE %s.float_values (part text, id int, val1 double, val2 float, '
                             'PRIMARY KEY (part, id))' % (self.ks,))
        # the literals go through the server's parser, as in cqlsh, not the driver's float conversion
        for i, (part, literal, _, _) in enumerate(rows):
            self.session.execute("INSERT INTO %s.float_values (part, id, val1, val2) VALUES ('%s', %d, %s, %s)"
                                 % (self.ks, part, i, literal, literal))

        printed = {int(i): (val1, val2) for _, i, val1, val2 in self.select_rows('SELECT * FROM float_values;')}
        expected = {i: (printed_double, printed_float) for i, (_, _, printed_double, printed_float) in enumerate(rows)}
        self.assertEqual(printed, expected)

    def test_int_values(self):  # CASSANDRA-9399
        output = self.run_cqlsh("""
            CREATE TABLE int_values (part text PRIMARY KEY, val1 int, val2 bigint, val3 smallint, val4 tinyint);
            INSERT INTO int_values (part, val1, val2, val3, val4) VALUES ('1', 1, 1, 1, 1);
            INSERT INTO int_values (part, val1, val2, val3, val4) VALUES ('0', 0, 0, 0, 0);
            INSERT INTO int_values (part, val1, val2, val3, val4) VALUES ('min', %d, %d, -32768, -128);
            INSERT INTO int_values (part, val1, val2, val3, val4) VALUES ('max', %d, %d, 32767, 127);
            """ % (-1 << 31, -1 << 63, (1 << 31) - 1, (1 << 63) - 1))
        self.assertEqual(output.strip(), '')

        rows = self.select_rows('SELECT * FROM int_values;')
        self.assertCountEqual(rows, [
            ['min', '-2147483648', '-9223372036854775808', '-32768', '-128'],
            ['max', '2147483647', '9223372036854775807', '32767', '127'],
            ['0', '0', '0', '0', '0'],
            ['1', '1', '1', '1', '1'],
        ])

    def test_datetime_values(self):  # CASSANDRA-9399
        self.session.execute('CREATE TABLE %s.datetime_values (d date, t time, PRIMARY KEY (d, t))' % (self.ks,))
        insert = self.session.prepare('INSERT INTO %s.datetime_values (d, t) VALUES (?, ?)' % (self.ks,))
        # the servers do not parse the same literals for years 0 and 10000, so the dates are sent as day counts
        execute_concurrent_with_args(self.session, insert, [
            (Date(-719528), Time('00:00:00.000000000')),  # 0000-01-01
            (Date(datetime.date(datetime.MINYEAR, 1, 1)), Time('01:00:00.000000000')),
            (Date(datetime.date(1582, 1, 1)), Time('00:00:00.000000000')),
            (Date(datetime.date(2015, 5, 14)), Time('16:30:00.555555555')),
            (Date(datetime.date(9800, 12, 31)), Time('23:59:59.999999999')),
            (Date(datetime.date(datetime.MAXYEAR, 1, 1)), Time('02:00:00.000000000')),
            (Date(2932897), Time('03:00:00.000000000')),  # 10000-01-01
        ])

        rows = self.select_rows('SELECT * FROM datetime_values;')
        self.assertCountEqual(rows, [
            # outside of Python's datetime range, a date is printed as its number of days since the epoch
            ['-719528', '00:00:00.000000000'],
            ['0001-01-01', '01:00:00.000000000'],
            ['1582-01-01', '00:00:00.000000000'],
            ['2015-05-14', '16:30:00.555555555'],
            ['9800-12-31', '23:59:59.999999999'],
            ['9999-01-01', '02:00:00.000000000'],
            ['2932897', '03:00:00.000000000'],
        ])

    def test_tracing(self):  # CASSANDRA-9399
        # checks that tracing does not break the query output; the trace itself comes from the server
        self.session.execute('CREATE TABLE %s.tracing_values (id int PRIMARY KEY, val text)' % (self.ks,))
        for i, val in enumerate(('adfad', 'lkjlk', 'iuiou'), start=1):
            self.session.execute("INSERT INTO %s.tracing_values (id, val) VALUES (%d, '%s')" % (self.ks, i, val))

        output = self.run_cqlsh('TRACING ON; SELECT * FROM tracing_values;')
        self.assertIn('Now Tracing is enabled', output)
        self.assertIn(dedent("""
             id | val
            ----+-------
              1 | adfad
              2 | lkjlk
              3 | iuiou

            (3 rows)

            Tracing session: """), output)
        self.assertRegex(output, r'activity\s+\| timestamp\s+\| source\s+\| source_elapsed\s+\| client')

    def test_tracing_from_system_traces(self):
        self.session.execute('CREATE TABLE %s.traced (key int PRIMARY KEY, c1 text, c2 text)' % (self.ks,))
        insert = self.session.prepare('INSERT INTO %s.traced (key, c1, c2) VALUES (?, ?, ?)' % (self.ks,))
        execute_concurrent_with_args(self.session, insert, [(i, 'value1', 'value2') for i in range(10)])

        output = self.run_cqlsh('TRACING ON; SELECT * FROM traced;')
        self.assertIn('Tracing session: ', output)

        # queries on the trace tables are not traced, whether the keyspace is named or current
        output = self.run_cqlsh('TRACING ON; SELECT * FROM system_traces.events LIMIT 10;')
        self.assertIn('Now Tracing is enabled', output)
        self.assertIn('rows)', output)
        self.assertNotIn('Tracing session: ', output)
        output = self.run_cqlsh('TRACING ON; USE system_traces; SELECT * FROM sessions LIMIT 10;')
        self.assertIn('rows)', output)
        self.assertNotIn('Tracing session: ', output)

    def test_select_element_inside_udt(self):  # CASSANDRA-7891
        self.session.execute('CREATE TYPE %s.address (street text, city text, zip_code int, phones set<text>)'
                             % (self.ks,))
        self.session.execute('CREATE TYPE %s.fullname (firstname text, lastname text)' % (self.ks,))
        self.session.execute('CREATE TABLE %s.users (id uuid PRIMARY KEY, name frozen<fullname>, '
                             'addresses map<text, frozen<address>>)' % (self.ks,))
        self.session.execute("INSERT INTO %s.users (id, name) VALUES (62c36092-82a1-3a00-93d1-46196ee77204, "
                             "{firstname: 'Marie-Claude', lastname: 'Josset'})" % (self.ks,))

        # cqlsh used to fail with "list index out of range" when printing a UDT field
        rows = self.select_rows('SELECT name.lastname FROM users WHERE id = 62c36092-82a1-3a00-93d1-46196ee77204;')
        self.assertEqual(rows, [['Josset']])

    def test_connect_timeout(self):  # CASSANDRA-9601
        output = self.run_cqlsh('USE system;', args=('--debug', '--connect-timeout=10'))
        self.assertIn('Using connect timeout: 10 seconds', output)

    def check_clear_screen(self, cmd):
        # CLEAR runs the clear command, which writes the terminfo sequence of $TERM
        env = dict(self.env, TERM='xterm')
        with run_cqlsh_for_test(tty=True, env=env) as c:
            c.send(cmd + '\n')
            # the prompt follows the sequence on the same line, so cmd_and_response() would not find it
            output = c.read_until(r'cqlsh(:\S+)?> ', timeout=10.0)
        # one of the "erase in display" sequences: ESC[J, ESC[0J, ESC[1J or ESC[2J
        self.assertRegex(output, '\x1b\\[[012]?J')
        self.assertNotIn('Error', output)

    def test_clear(self):  # CASSANDRA-10086
        self.check_clear_screen('CLEAR')
