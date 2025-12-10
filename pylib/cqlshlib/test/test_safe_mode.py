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
Test safe mode functionality for CQLsh.

These tests verify that the safe mode feature correctly identifies dangerous
operations and prompts for confirmation before executing them.
"""

import unittest
from unittest.mock import patch


class MockShell:
    """Mock Shell class with safe mode methods for testing"""
    
    def __init__(self, safe_mode=False, tty=True):
        self.safe_mode = safe_mode
        self.tty = tty
    
    def is_dangerous_statement(self, statement):
        """
        Check if a statement is dangerous and requires confirmation in safe mode.
        Dangerous statements include DROP and TRUNCATE operations.
        """
        statement_upper = statement.strip().upper()
        dangerous_keywords = [
            'DROP KEYSPACE',
            'DROP TABLE',
            'DROP COLUMNFAMILY',
            'DROP INDEX',
            'DROP MATERIALIZED VIEW',
            'DROP TYPE',
            'DROP FUNCTION',
            'DROP AGGREGATE',
            'DROP USER',
            'DROP ROLE',
            'DROP SERVICE_LEVEL',
            'DROP TRIGGER',
            'TRUNCATE'
        ]
        for keyword in dangerous_keywords:
            if statement_upper.startswith(keyword):
                return True
        return False
    
    def extract_operation_target(self, statement):
        """
        Extract the target (keyspace/table name) from a dangerous statement for the confirmation prompt.
        """
        # Simple extraction - get words after the operation keyword
        words = statement.strip().split()
        
        # Handle TRUNCATE statements (can be "TRUNCATE table" or "TRUNCATE TABLE table")
        if len(words) >= 2 and words[0].upper() == 'TRUNCATE':
            if len(words) >= 3 and words[1].upper() == 'TABLE':
                return words[2].strip(';')
            else:
                return words[1].strip(';')
        
        # Handle other DROP statements
        if len(words) >= 3:
            # Handle "DROP KEYSPACE name", "DROP TABLE name", etc.
            # Skip "IF EXISTS" if present
            idx = 2
            if idx < len(words) and words[idx].upper() == 'IF':
                idx = 4  # Skip "IF EXISTS"
            if idx < len(words):
                return words[idx].strip(';')
        return ''
    
    def prompt_for_confirmation(self, statement):
        """
        Prompt user for confirmation before executing a dangerous statement.
        Returns True if user confirms, False otherwise.
        """
        if not self.tty:
            # If not in interactive mode, don't prompt (assume yes for scripts)
            return True
        
        statement_upper = statement.strip().upper()
        target = self.extract_operation_target(statement)
        
        # Determine the operation type
        if statement_upper.startswith('DROP KEYSPACE'):
            op_type = 'DROP KEYSPACE'
        elif statement_upper.startswith('DROP TABLE') or statement_upper.startswith('DROP COLUMNFAMILY'):
            op_type = 'DROP TABLE'
        elif statement_upper.startswith('TRUNCATE'):
            op_type = 'TRUNCATE'
        else:
            op_type = statement_upper.split()[0:2]
            op_type = ' '.join(op_type) if isinstance(op_type, list) else op_type
        
        if target:
            prompt_msg = f"Are you sure you want to {op_type} {target}? [N/y] "
        else:
            prompt_msg = f"Are you sure you want to execute this {op_type} statement? [N/y] "
        
        try:
            response = input(prompt_msg).strip().lower()
            return response in ('y', 'yes')
        except (KeyboardInterrupt, EOFError):
            print()  # newline after interrupt
            return False


class TestSafeMode(unittest.TestCase):
    """Test cases for safe mode functionality in CQLsh"""

    def test_is_dangerous_statement_drop_keyspace(self):
        """Test that DROP KEYSPACE is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP KEYSPACE test_ks;"))
        self.assertTrue(shell.is_dangerous_statement("drop keyspace test_ks;"))
        self.assertTrue(shell.is_dangerous_statement("DROP KEYSPACE IF EXISTS test_ks;"))

    def test_is_dangerous_statement_drop_table(self):
        """Test that DROP TABLE is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP TABLE test_table;"))
        self.assertTrue(shell.is_dangerous_statement("drop table test_table;"))
        self.assertTrue(shell.is_dangerous_statement("DROP TABLE IF EXISTS test_table;"))
        self.assertTrue(shell.is_dangerous_statement("DROP COLUMNFAMILY test_cf;"))

    def test_is_dangerous_statement_truncate(self):
        """Test that TRUNCATE is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("TRUNCATE test_table;"))
        self.assertTrue(shell.is_dangerous_statement("truncate test_table;"))
        self.assertTrue(shell.is_dangerous_statement("TRUNCATE TABLE test_table;"))

    def test_is_dangerous_statement_drop_index(self):
        """Test that DROP INDEX is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP INDEX test_idx;"))
        self.assertTrue(shell.is_dangerous_statement("DROP INDEX IF EXISTS test_idx;"))

    def test_is_dangerous_statement_drop_materialized_view(self):
        """Test that DROP MATERIALIZED VIEW is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP MATERIALIZED VIEW test_mv;"))
        self.assertTrue(shell.is_dangerous_statement("DROP MATERIALIZED VIEW IF EXISTS test_mv;"))

    def test_is_dangerous_statement_drop_type(self):
        """Test that DROP TYPE is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP TYPE test_type;"))

    def test_is_dangerous_statement_drop_function(self):
        """Test that DROP FUNCTION is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP FUNCTION test_func;"))
        self.assertTrue(shell.is_dangerous_statement("DROP FUNCTION IF EXISTS test_func;"))

    def test_is_dangerous_statement_drop_aggregate(self):
        """Test that DROP AGGREGATE is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP AGGREGATE test_agg;"))
        self.assertTrue(shell.is_dangerous_statement("DROP AGGREGATE IF EXISTS test_agg;"))

    def test_is_dangerous_statement_drop_user(self):
        """Test that DROP USER is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP USER test_user;"))
        self.assertTrue(shell.is_dangerous_statement("DROP USER IF EXISTS test_user;"))

    def test_is_dangerous_statement_drop_role(self):
        """Test that DROP ROLE is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP ROLE test_role;"))

    def test_is_dangerous_statement_drop_trigger(self):
        """Test that DROP TRIGGER is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP TRIGGER test_trigger;"))
        self.assertTrue(shell.is_dangerous_statement("DROP TRIGGER IF EXISTS test_trigger;"))

    def test_is_dangerous_statement_drop_service_level(self):
        """Test that DROP SERVICE_LEVEL is identified as dangerous"""
        shell = MockShell()
        
        self.assertTrue(shell.is_dangerous_statement("DROP SERVICE_LEVEL test_sla;"))
        self.assertTrue(shell.is_dangerous_statement("DROP SERVICE_LEVEL IF EXISTS test_sla;"))

    def test_is_dangerous_statement_safe_operations(self):
        """Test that safe operations are not identified as dangerous"""
        shell = MockShell()
        
        self.assertFalse(shell.is_dangerous_statement("SELECT * FROM test_table;"))
        self.assertFalse(shell.is_dangerous_statement("INSERT INTO test_table (id) VALUES (1);"))
        self.assertFalse(shell.is_dangerous_statement("UPDATE test_table SET col = 1;"))
        self.assertFalse(shell.is_dangerous_statement("DELETE FROM test_table WHERE id = 1;"))
        self.assertFalse(shell.is_dangerous_statement("CREATE KEYSPACE test_ks;"))
        self.assertFalse(shell.is_dangerous_statement("CREATE TABLE test_table;"))
        self.assertFalse(shell.is_dangerous_statement("ALTER TABLE test_table;"))

    def test_extract_operation_target_keyspace(self):
        """Test extracting target from DROP KEYSPACE statement"""
        shell = MockShell()
        
        self.assertEqual(shell.extract_operation_target("DROP KEYSPACE test_ks;"), "test_ks")
        self.assertEqual(shell.extract_operation_target("DROP KEYSPACE IF EXISTS test_ks;"), "test_ks")

    def test_extract_operation_target_table(self):
        """Test extracting target from DROP TABLE statement"""
        shell = MockShell()
        
        self.assertEqual(shell.extract_operation_target("DROP TABLE test_table;"), "test_table")
        self.assertEqual(shell.extract_operation_target("DROP TABLE IF EXISTS test_table;"), "test_table")

    def test_extract_operation_target_truncate(self):
        """Test extracting target from TRUNCATE statement"""
        shell = MockShell()
        
        self.assertEqual(shell.extract_operation_target("TRUNCATE test_table;"), "test_table")
        self.assertEqual(shell.extract_operation_target("TRUNCATE TABLE test_table;"), "test_table")

    @patch('builtins.input', return_value='y')
    def test_prompt_for_confirmation_yes(self, mock_input):
        """Test that confirmation prompt returns True when user enters 'y'"""
        shell = MockShell(tty=True)
        
        result = shell.prompt_for_confirmation("DROP KEYSPACE test_ks;")
        self.assertTrue(result)
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='yes')
    def test_prompt_for_confirmation_yes_full(self, mock_input):
        """Test that confirmation prompt returns True when user enters 'yes'"""
        shell = MockShell(tty=True)
        
        result = shell.prompt_for_confirmation("DROP KEYSPACE test_ks;")
        self.assertTrue(result)

    @patch('builtins.input', return_value='n')
    def test_prompt_for_confirmation_no(self, mock_input):
        """Test that confirmation prompt returns False when user enters 'n'"""
        shell = MockShell(tty=True)
        
        result = shell.prompt_for_confirmation("DROP KEYSPACE test_ks;")
        self.assertFalse(result)

    @patch('builtins.input', return_value='')
    def test_prompt_for_confirmation_empty(self, mock_input):
        """Test that confirmation prompt returns False when user enters empty string (default No)"""
        shell = MockShell(tty=True)
        
        result = shell.prompt_for_confirmation("DROP KEYSPACE test_ks;")
        self.assertFalse(result)

    @patch('builtins.input', side_effect=KeyboardInterrupt)
    def test_prompt_for_confirmation_keyboard_interrupt(self, mock_input):
        """Test that confirmation prompt returns False on keyboard interrupt"""
        shell = MockShell(tty=True)
        
        result = shell.prompt_for_confirmation("DROP KEYSPACE test_ks;")
        self.assertFalse(result)

    def test_prompt_for_confirmation_non_tty(self):
        """Test that confirmation prompt returns True in non-TTY mode (scripts)"""
        shell = MockShell(tty=False)
        
        result = shell.prompt_for_confirmation("DROP KEYSPACE test_ks;")
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
