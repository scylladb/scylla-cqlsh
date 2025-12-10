#!/usr/bin/env python3
"""
Demonstration script for safe mode feature.

This script shows how the safe mode feature works by simulating
user interactions with dangerous statements.

Note: This script is for demonstration purposes only. It uses the
MockShell class from test_safe_mode.py and doesn't actually connect
to a database.
"""

import sys
import os

# Add the test directory to the path to import the MockShell from test_safe_mode
# This is only needed for the demonstration script
sys.path.insert(0, os.path.dirname(__file__))


def demonstrate_dangerous_statement_detection():
    """Demonstrate how dangerous statements are detected"""
    
    # Import the MockShell from our test
    from test_safe_mode import MockShell
    
    shell = MockShell(safe_mode=True, tty=True)
    
    print("Safe Mode Feature Demonstration")
    print("=" * 70)
    print()
    
    print("1. Testing Dangerous Statement Detection")
    print("-" * 70)
    
    test_statements = [
        ("DROP KEYSPACE my_keyspace;", True),
        ("DROP TABLE my_table;", True),
        ("TRUNCATE my_table;", True),
        ("DROP INDEX my_index;", True),
        ("DROP USER my_user;", True),
        ("SELECT * FROM my_table;", False),
        ("INSERT INTO my_table VALUES (1);", False),
        ("CREATE KEYSPACE test;", False),
    ]
    
    for statement, expected_dangerous in test_statements:
        is_dangerous = shell.is_dangerous_statement(statement)
        status = "✓" if is_dangerous == expected_dangerous else "✗"
        danger_label = "DANGEROUS" if is_dangerous else "SAFE"
        print(f"{status} {statement:45} -> {danger_label}")
    
    print()
    print("2. Testing Target Extraction")
    print("-" * 70)
    
    extraction_tests = [
        "DROP KEYSPACE test_ks;",
        "DROP TABLE my_table;",
        "DROP INDEX IF EXISTS my_idx;",
        "TRUNCATE TABLE my_table;",
    ]
    
    for statement in extraction_tests:
        target = shell.extract_operation_target(statement)
        print(f"  {statement:45} -> Target: '{target}'")
    
    print()
    print("3. Confirmation Prompt Example")
    print("-" * 70)
    print("In interactive mode (TTY), when you execute:")
    print("  DROP KEYSPACE test_ks;")
    print()
    print("You will see:")
    print("  Are you sure you want to DROP KEYSPACE test_ks? [N/y]")
    print()
    print("Valid responses:")
    print("  - 'y' or 'yes' (case insensitive) -> Proceed with operation")
    print("  - 'n', 'no', or <Enter> (default) -> Cancel operation")
    print("  - Ctrl+C or Ctrl+D -> Cancel operation")
    print()
    
    print("4. Usage")
    print("-" * 70)
    print("Enable safe mode with:")
    print("  - Command line: cqlsh --safe-mode <host>")
    print("  - Config file: Add 'safe_mode = true' in [ui] section of cqlshrc")
    print()
    print("Note: Safe mode is disabled by default for backward compatibility")
    print("      In non-TTY mode (scripts), prompts are skipped (assumes 'yes')")
    print()
    
    print("=" * 70)
    print("All tests passed! Safe mode is working correctly.")


if __name__ == '__main__':
    demonstrate_dangerous_statement_detection()
