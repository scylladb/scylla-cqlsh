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

from .basecase import BaseTestCase, cqlsh_env_in_utc
from .cassconnect import create_keyspace, get_cassandra_connection, get_keyspace, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test


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
        env = cqlsh_env_in_utc()
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
