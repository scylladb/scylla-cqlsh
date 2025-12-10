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
Test for roundtrip consistency between formatting and parsing of escape sequences.

This test validates that what cqlsh displays can be used as input to query the same data.
"""

import unittest
from cqlshlib.formatting import format_value_text, unicode_controlchars_re, _show_control_chars
from cqlshlib.cql3handling import dequote_value
from cqlshlib.displaying import NO_COLOR_MAP
from cqlshlib.formatting import CqlType


class TestEscapeRoundtrip(unittest.TestCase):
    """
    Test that the format displayed by cqlsh can be parsed back to the same value.
    This addresses the core issue: cqlsh shows '\x01' but doesn't accept it as input.
    """

    def format_text_value(self, val):
        """Format a text value as cqlsh would display it."""
        # This mimics what format_value_text does for display
        escapedval = val.replace('\\', '\\\\')
        escapedval = unicode_controlchars_re.sub(_show_control_chars, escapedval)
        return escapedval

    def test_control_chars_roundtrip(self):
        """Test that control characters can roundtrip through display and parsing."""
        test_cases = [
            '\x01',  # control-A
            '\x00',  # null byte
            '\x09',  # tab
            '\x0a',  # newline
            '\x0d',  # carriage return
            '\x1f',  # unit separator
            '\x7f',  # delete
        ]

        for original in test_cases:
            # Format the value as cqlsh would display it
            displayed = self.format_text_value(original)
            
            # Now parse it back using dequote_value (which users would do when querying)
            # We need to wrap it in quotes as it would be in a query
            parsed = dequote_value(f"'{displayed}'")
            
            # Should match the original
            self.assertEqual(parsed, original,
                f"Roundtrip failed for {original!r}: displayed as {displayed!r}, parsed back as {parsed!r}")

    def test_embedded_control_chars_roundtrip(self):
        """Test that control characters embedded in strings roundtrip correctly."""
        test_cases = [
            'hello\x01world',
            'test\x00data',
            'multi\nline\ntext',
            'tab\tseparated\tvalues',
        ]

        for original in test_cases:
            displayed = self.format_text_value(original)
            parsed = dequote_value(f"'{displayed}'")
            self.assertEqual(parsed, original,
                f"Roundtrip failed for {original!r}: displayed as {displayed!r}, parsed back as {parsed!r}")

    def test_literal_backslash_roundtrip(self):
        """Test that literal backslashes are handled correctly."""
        test_cases = [
            '\\',  # single backslash
            'path\\to\\file',  # Windows-style path
            '\\x00',  # literal string \x00 (not a null byte)
        ]

        for original in test_cases:
            displayed = self.format_text_value(original)
            parsed = dequote_value(f"'{displayed}'")
            self.assertEqual(parsed, original,
                f"Roundtrip failed for {original!r}: displayed as {displayed!r}, parsed back as {parsed!r}")

    def test_mixed_content_roundtrip(self):
        """Test strings with mixed content (normal chars, control chars, backslashes)."""
        test_cases = [
            'normal text',
            'text with \x01 control',
            'text\\with\\backslashes',
            'combo\x01\\mix\x02end',
        ]

        for original in test_cases:
            displayed = self.format_text_value(original)
            parsed = dequote_value(f"'{displayed}'")
            self.assertEqual(parsed, original,
                f"Roundtrip failed for {original!r}: displayed as {displayed!r}, parsed back as {parsed!r}")

    def test_example_from_issue(self):
        """Test the specific example from the issue report."""
        # The issue shows that '\x01' is displayed for control-A
        # but querying with '\x01' doesn't work
        control_a = '\x01'
        
        # Format as cqlsh would display it
        displayed = self.format_text_value(control_a)
        self.assertEqual(displayed, '\\x01', "Control-A should be displayed as \\x01")
        
        # Parse it back
        parsed = dequote_value(f"'{displayed}'")
        self.assertEqual(parsed, control_a, "Parsing '\\x01' should give control-A")

    def test_all_control_chars(self):
        """Test all control characters that cqlsh escapes."""
        # Test all chars from 0x00 to 0x1f and 0x7f to 0xa0
        for byte_val in list(range(0x00, 0x20)) + list(range(0x7f, 0xa1)):
            original = chr(byte_val)
            displayed = self.format_text_value(original)
            parsed = dequote_value(f"'{displayed}'")
            self.assertEqual(parsed, original,
                f"Roundtrip failed for byte 0x{byte_val:02x}: displayed as {displayed!r}, parsed back as {parsed!r}")


if __name__ == '__main__':
    unittest.main()
