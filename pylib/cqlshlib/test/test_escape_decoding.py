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
Unit tests for escape sequence handling in cql3handling module.
"""

import unittest
from cqlshlib.cql3handling import decode_escape_sequences, dequote_value


class TestEscapeSequenceDecoding(unittest.TestCase):

    def test_hex_escape_sequences(self):
        """Test that hex escape sequences are properly decoded."""
        # Test single byte hex values
        self.assertEqual(decode_escape_sequences('\\x01'), '\x01')
        self.assertEqual(decode_escape_sequences('\\x00'), '\x00')
        self.assertEqual(decode_escape_sequences('\\x0a'), '\n')
        self.assertEqual(decode_escape_sequences('\\x09'), '\t')
        self.assertEqual(decode_escape_sequences('\\x0d'), '\r')
        self.assertEqual(decode_escape_sequences('\\x1f'), '\x1f')
        self.assertEqual(decode_escape_sequences('\\x7f'), '\x7f')
        self.assertEqual(decode_escape_sequences('\\xff'), '\xff')

    def test_hex_escape_in_string(self):
        """Test hex escapes within regular strings."""
        self.assertEqual(decode_escape_sequences('hello\\x01world'), 'hello\x01world')
        self.assertEqual(decode_escape_sequences('\\x01test\\x02'), '\x01test\x02')

    def test_standard_escape_sequences(self):
        """Test standard escape sequences like \n, \r, \t."""
        self.assertEqual(decode_escape_sequences('\\n'), '\n')
        self.assertEqual(decode_escape_sequences('\\r'), '\r')
        self.assertEqual(decode_escape_sequences('\\t'), '\t')
        self.assertEqual(decode_escape_sequences('line1\\nline2'), 'line1\nline2')

    def test_backslash_escaping(self):
        """Test that double backslashes produce a single backslash."""
        self.assertEqual(decode_escape_sequences('\\\\'), '\\')
        self.assertEqual(decode_escape_sequences('\\\\x00'), '\\x00')  # literal \x00
        self.assertEqual(decode_escape_sequences('\\\\\\x01'), '\\\x01')  # backslash + control-A

    def test_quote_escaping(self):
        """Test that escaped quotes work correctly."""
        self.assertEqual(decode_escape_sequences("\\'"), "'")

    def test_no_escapes(self):
        """Test strings without escape sequences."""
        self.assertEqual(decode_escape_sequences('hello'), 'hello')
        self.assertEqual(decode_escape_sequences('normal string'), 'normal string')

    def test_invalid_hex_escape(self):
        """Test that invalid hex sequences are treated as literals."""
        # Not enough digits
        self.assertEqual(decode_escape_sequences('\\x'), '\\x')
        self.assertEqual(decode_escape_sequences('\\x0'), '\\x0')
        # Invalid hex digits
        self.assertEqual(decode_escape_sequences('\\xgg'), '\\xgg')

    def test_dequote_value_with_escapes(self):
        """Test dequote_value handles escape sequences correctly."""
        self.assertEqual(dequote_value("'\\x01'"), '\x01')
        self.assertEqual(dequote_value("'hello\\x01world'"), 'hello\x01world')
        self.assertEqual(dequote_value("'line1\\nline2'"), 'line1\nline2')
        
    def test_dequote_value_with_literal_backslash(self):
        """Test dequote_value handles literal backslashes."""
        self.assertEqual(dequote_value("'\\\\x00'"), '\\x00')

    def test_dequote_value_without_quotes(self):
        """Test dequote_value on unquoted strings (no escape processing)."""
        # Unquoted strings should not have escape processing
        self.assertEqual(dequote_value('\\x01'), '\\x01')

    def test_multiple_escapes(self):
        """Test strings with multiple escape sequences."""
        self.assertEqual(
            decode_escape_sequences('\\x01\\x02\\x03'),
            '\x01\x02\x03'
        )
        self.assertEqual(
            decode_escape_sequences('\\n\\r\\t'),
            '\n\r\t'
        )

    def test_hex_escape_at_end_of_string(self):
        """Test that hex escape sequences at the end of a string work correctly."""
        # This tests the boundary condition fixed in the code review
        self.assertEqual(decode_escape_sequences('test\\xff'), 'test\xff')
        self.assertEqual(decode_escape_sequences('\\x00'), '\x00')
        self.assertEqual(decode_escape_sequences('a\\x01'), 'a\x01')


if __name__ == '__main__':
    unittest.main()
