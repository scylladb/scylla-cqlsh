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

"""
Batch (non-tty) input handling: large multi-line statements must not be
re-parsed on every line (https://github.com/scylladb/scylla-cqlsh/issues/42),
while newline-terminated commands keep working.
"""

import os

from .basecase import BaseTestCase
from .cassconnect import cassandra_cursor, create_db, get_keyspace, remove_db
from .cassconnect import testcall_cqlsh as call_cqlsh_for_test

# before the fix each of these took minutes to hours
TIME_LIMIT = 30


class TestBatchInput(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        create_db()
        cls.ks = get_keyspace()
        with cassandra_cursor(ks=cls.ks) as c:
            c.execute('CREATE TABLE batch_input (k int PRIMARY KEY, v text)')

    @classmethod
    def tearDownClass(cls):
        remove_db()

    def run_cqlsh(self, cql):
        return call_cqlsh_for_test(input=cql, keyspace=self.ks, env=os.environ.copy(), timeout=TIME_LIMIT)

    def select_v(self, k):
        with cassandra_cursor(ks=self.ks) as c:
            return c.execute('SELECT v FROM batch_input WHERE k = %s', (k,)).one()[0]

    def test_large_multiline_statement(self):
        # same shape as the 1.1MB / 32k-line WASM (text format) UDF from issue #42:
        # one big multi-line string literal, with ';' inside
        value = '(module\n' + '\n'.join(
            f'  (type (;{i};) (func (param i32 i32) (result i32)))' for i in range(32000)) + ')'
        output, result = self.run_cqlsh(f"INSERT INTO batch_input (k, v) VALUES (1, '{value}');\n")
        self.assertEqual(0, result, output)
        self.assertEqual('', output)
        self.assertEqual(value, self.select_v(1))

    def test_newline_terminated_commands_and_comments(self):
        output, result = self.run_cqlsh(
            "CONSISTENCY ONE\n"
            "EXPAND ON\n"
            "/* block\n"
            "   comment; */\n"
            "INSERT INTO batch_input (k, v)\n"
            "  VALUES (3, 'three'); -- trailing comment\n"
            "SELECT v FROM batch_input WHERE k = 3;\n"
            # a block comment right after a statement with a trailing comment
            "INSERT INTO batch_input (k, v)\n"
            "  VALUES (4, 'four'); -- seed\n"
            "/* disabled:\n"
            "  DELETE FROM batch_input WHERE k = 4;\n"
            "*/\n"
            "INSERT INTO batch_input (k, v)\n"
            "  VALUES (5, 'five'); -- seed\n"
            "/*\n"
            " * Section\n"
            " */\n"
            "INSERT INTO batch_input (k, v) VALUES (6, 'six');\n")
        self.assertEqual(0, result, output)
        self.assertIn('Consistency level set to ONE', output)
        self.assertIn('@ Row 1', output)
        self.assertEqual('three', self.select_v(3))
        self.assertEqual('four', self.select_v(4))
        self.assertEqual('six', self.select_v(6))

    def test_exit_on_continuation_line(self):
        output, result = self.run_cqlsh(
            "INSERT INTO batch_input (k, v)\n"
            "  VALUES (7, 'seven'); EXIT\n"
            "DELETE FROM batch_input WHERE k = 7;\n")
        self.assertEqual(0, result, output)
        self.assertEqual('', output)
        self.assertEqual('seven', self.select_v(7))

        # same after a "/*" left open behind a complete statement, with a quote inside it
        output, result = self.run_cqlsh(
            "INSERT INTO batch_input (k, v) VALUES (9, 'nine'); /* note\n"
            "   don't\n"
            "*/ EXIT\n"
            "DELETE FROM batch_input WHERE k = 9;\n")
        self.assertEqual(0, result, output)
        self.assertEqual('', output)
        self.assertEqual('nine', self.select_v(9))

    def test_statement_after_invalid_one_still_runs(self):
        output, _ = self.run_cqlsh(
            "INSERT INTO batch_input (k, v)\n"
            "  VALUES (@)\n"
            "INSERT INTO batch_input (k, v) VALUES (8, 'eight');\n")
        self.assertIn('Invalid syntax', output)
        self.assertEqual('eight', self.select_v(8))

        # same when the invalid line also opens a string literal
        output, _ = self.run_cqlsh(
            "INSERT INTO batch_input (k, v) VALUES (@, '\n"
            "INSERT INTO batch_input (k, v) VALUES (10, 'ten');\n")
        self.assertIn('Invalid syntax', output)
        self.assertEqual('ten', self.select_v(10))
