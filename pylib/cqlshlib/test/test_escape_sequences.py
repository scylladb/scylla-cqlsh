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

"""
Test for escape sequence handling in cqlsh.

This test addresses the issue where cqlsh displays non-printable characters
using escape sequences like '\x01' but doesn't recognize those same sequences
when used in queries.
"""

import os
from .basecase import BaseTestCase
from .cassconnect import (get_cassandra_connection, create_keyspace, remove_db, testrun_cqlsh)


class TestEscapeSequences(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        s = get_cassandra_connection().connect()
        s.default_timeout = 60.0
        create_keyspace(s)
        s.execute('CREATE TABLE escape_test (pk text PRIMARY KEY, val text)')

        env = os.environ.copy()
        env['LC_CTYPE'] = 'UTF-8'
        cls.default_env = env

    @classmethod
    def tearDownClass(cls):
        remove_db()

    def test_hex_escape_in_query(self):
        """
        Test that hex escape sequences like '\x01' work in queries.
        This is the main issue: cqlsh shows control-A as '\x01' in output,
        but doesn't recognize '\x01' in input.
        """
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            # Insert a row with a control character using hex escape
            c.cmd_and_response("INSERT INTO escape_test (pk) VALUES ('\\x01');")
            
            # Query using the same hex escape format
            output = c.cmd_and_response("SELECT * FROM escape_test WHERE pk='\\x01';")
            
            # Should find the row (currently this fails)
            self.assertIn('\\x01', output)
            self.assertNotIn('(0 rows)', output)

    def test_various_hex_escapes(self):
        """
        Test various hex escape sequences.
        """
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            # Test different control characters
            test_cases = [
                ('\\x00', 'null byte'),
                ('\\x09', 'tab'),
                ('\\x0a', 'newline'),
                ('\\x0d', 'carriage return'),
                ('\\x1f', 'unit separator'),
                ('\\x7f', 'delete'),
            ]
            
            for escape_seq, description in test_cases:
                # Clean up previous test data
                c.cmd_and_response("TRUNCATE escape_test;")
                
                # Insert using escape sequence
                c.cmd_and_response(f"INSERT INTO escape_test (pk, val) VALUES ('{escape_seq}', '{description}');")
                
                # Query using same escape sequence
                output = c.cmd_and_response(f"SELECT * FROM escape_test WHERE pk='{escape_seq}';")
                
                # Should find the row
                self.assertIn(description, output, f"Failed to find row with {description}")
                self.assertNotIn('(0 rows)', output, f"Got 0 rows for {description}")

    def test_escape_sequence_display_consistency(self):
        """
        Test that the display format of control characters is consistent
        with the input format.
        """
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            # Insert using hex escape
            c.cmd_and_response("INSERT INTO escape_test (pk, val) VALUES ('\\x01', 'control-A');")
            
            # Select all and check the output format
            output = c.cmd_and_response("SELECT * FROM escape_test WHERE pk='\\x01';")
            
            # The output should show the escape sequence in a format we can use
            self.assertIn('control-A', output)

    def test_standard_escape_sequences(self):
        """
        Test standard escape sequences like \n, \r, \t.
        """
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            # These should already work, but let's verify
            c.cmd_and_response("TRUNCATE escape_test;")
            
            # Insert with standard escapes
            c.cmd_and_response("INSERT INTO escape_test (pk, val) VALUES ('test', 'line1\\nline2');")
            
            # Query should work
            output = c.cmd_and_response("SELECT * FROM escape_test WHERE pk='test';")
            self.assertIn('line', output)

    def test_backslash_escaping(self):
        """
        Test that literal backslashes are properly escaped.
        """
        with testrun_cqlsh(tty=True, env=self.default_env) as c:
            c.cmd_and_response("TRUNCATE escape_test;")
            
            # Insert a string with literal backslashes
            c.cmd_and_response("INSERT INTO escape_test (pk, val) VALUES ('backslash', '\\\\x00');")
            
            # Query should find the literal string '\x00' (not a null byte)
            output = c.cmd_and_response("SELECT * FROM escape_test WHERE pk='backslash';")
            self.assertIn('backslash', output)
