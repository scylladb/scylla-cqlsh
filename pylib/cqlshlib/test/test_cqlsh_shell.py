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

from .basecase import BaseTestCase
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
