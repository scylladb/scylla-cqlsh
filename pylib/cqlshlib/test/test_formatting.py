# coding=utf-8
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

import os
import string

from .basecase import BaseTestCase
from .cassconnect import (get_cassandra_connection, create_keyspace, remove_db, testrun_cqlsh)


class TestFormatting(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        s = get_cassandra_connection().connect()
        s.default_timeout = 60.0
        create_keyspace(s)
        s.execute('CREATE TABLE t (k int PRIMARY KEY, v text)')

        env = os.environ.copy()
        env['LC_CTYPE'] = 'UTF-8'
        cls.default_env = env

    @classmethod
    def tearDownClass(cls):
        remove_db()

    def test_multiple_semicolons_in_describe(self):
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            v1 = 'type_name'
            v2 = 'value_name'
            _ = c.cmd_and_response(f'CREATE TYPE "{v1}" ( "{v2}" int );')
            output = c.cmd_and_response('DESC TYPES;;;')
            self.assertIn(v1, output)
            output = c.cmd_and_response(f'DESC TYPE "{v1}";;;')
            self.assertIn(v2, output)

    def test_spaces_in_describe(self):
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            v1 = 'type_name'
            v2 = 'value_name'
            _ = c.cmd_and_response(f'CREATE TYPE "{v1}" ( "{v2}" int );')

            def verify_output(prefix_str: str, infix_str: str, suffix_str: str) -> None:
                output = c.cmd_and_response(f'DESC{prefix_str}TYPES{suffix_str};')
                self.assertIn(v1, output)
                output = c.cmd_and_response(f'DESC{prefix_str}TYPE{infix_str}"{v1}"{suffix_str};')
                self.assertIn(v2, output)

            # cqlsh doesn't work well with whitespace characters other than spaces apparently.
            spaces = [' ', '  ', '   ']
            for prefix in spaces:
                for infix in spaces:
                    for suffix in [*spaces, '']:
                        verify_output(prefix, infix, suffix)
