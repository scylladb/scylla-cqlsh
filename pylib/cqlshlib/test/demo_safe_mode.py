#!/usr/bin/env python3
"""
Interactive demonstration of the safe mode feature.

This script simulates the CQLsh safe mode behavior, showing how
confirmation prompts work for dangerous operations without requiring
a database connection.

Run this script to see interactive examples of:
- How dangerous statements are detected
- How confirmation prompts appear
- How user responses are handled
"""

import sys
import os

# Add the test directory to the path to import the MockShell from test_safe_mode
sys.path.insert(0, os.path.dirname(__file__))


def simulate_interactive_session():
    """Simulate an interactive CQLsh session with safe mode enabled"""
    
    from test_safe_mode import MockShell
    
    print("=" * 80)
    print("CQLsh Safe Mode - Interactive Demonstration")
    print("=" * 80)
    print()
    print("This demo shows how safe mode protects you from accidental data loss.")
    print("You'll see confirmation prompts for dangerous operations.")
    print()
    print("=" * 80)
    print()
    
    # Create a shell instance with safe mode enabled
    shell = MockShell(safe_mode=True, tty=True)
    
    # Example scenarios to demonstrate
    scenarios = [
        {
            "statement": "DROP KEYSPACE production;",
            "description": "Scenario 1: Accidentally trying to drop production keyspace"
        },
        {
            "statement": "DROP TABLE users;",
            "description": "Scenario 2: Dropping a critical table"
        },
        {
            "statement": "TRUNCATE audit_log;",
            "description": "Scenario 3: Truncating all data from a table"
        },
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{scenario['description']}")
        print("-" * 80)
        print(f"cqlsh> {scenario['statement']}")
        
        # Check if statement is dangerous
        if shell.is_dangerous_statement(scenario['statement']):
            # Extract the target for better prompt
            target = shell.extract_operation_target(scenario['statement'])
            
            # Determine operation type
            statement_upper = scenario['statement'].strip().upper()
            if statement_upper.startswith('DROP KEYSPACE'):
                op_type = 'DROP KEYSPACE'
            elif statement_upper.startswith('DROP TABLE'):
                op_type = 'DROP TABLE'
            elif statement_upper.startswith('TRUNCATE'):
                op_type = 'TRUNCATE'
            else:
                op_type = scenario['statement'].split()[0:2]
                op_type = ' '.join(op_type)
            
            # Show the prompt
            if target:
                prompt_msg = f"Are you sure you want to {op_type} {target}? [N/y] "
            else:
                prompt_msg = f"Are you sure you want to execute this {op_type} statement? [N/y] "
            
            print(prompt_msg, end="")
            
            try:
                # Get user input
                response = input().strip().lower()
                
                if response in ('y', 'yes'):
                    print("✓ Operation would proceed (but no database is connected)")
                elif response == '':
                    print("✗ Operation cancelled (default is No)")
                else:
                    print("✗ Operation cancelled")
            except (KeyboardInterrupt, EOFError):
                print("\n✗ Operation cancelled (interrupted)")
        else:
            print("→ Safe operation, executes without confirmation")
        
        if i < len(scenarios):
            print("\n" + "─" * 80)
    
    print("\n\n" + "=" * 80)
    print("Additional Examples (non-interactive)")
    print("=" * 80)
    print()
    
    print("Safe operations that don't require confirmation:")
    safe_ops = [
        "SELECT * FROM users;",
        "INSERT INTO users (id, name) VALUES (1, 'John');",
        "UPDATE users SET status = 'active' WHERE id = 1;",
        "CREATE KEYSPACE test WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};",
    ]
    
    for op in safe_ops:
        is_dangerous = shell.is_dangerous_statement(op)
        print(f"  {'✓' if not is_dangerous else '✗'} {op}")
    
    print()
    print("Dangerous operations that require confirmation:")
    dangerous_ops = [
        "DROP KEYSPACE test_ks;",
        "DROP TABLE test_table;",
        "DROP INDEX test_idx;",
        "DROP MATERIALIZED VIEW test_mv;",
        "TRUNCATE sessions;",
        "DROP USER test_user;",
    ]
    
    for op in dangerous_ops:
        is_dangerous = shell.is_dangerous_statement(op)
        print(f"  {'✓' if is_dangerous else '✗'} {op}")
    
    print()
    print("=" * 80)
    print("Whitespace Handling")
    print("=" * 80)
    print()
    print("Safe mode is whitespace-insensitive and works correctly with:")
    whitespace_examples = [
        "DROP  KEYSPACE  test;",
        "  DROP TABLE test;",
        "DROP\tKEYSPACE\ttest;",
    ]
    
    for op in whitespace_examples:
        is_dangerous = shell.is_dangerous_statement(op)
        print(f"  {'✓' if is_dangerous else '✗'} {repr(op):40} -> {'DANGEROUS' if is_dangerous else 'SAFE'}")
    
    print()
    print("=" * 80)
    print("Configuration")
    print("=" * 80)
    print()
    print("Enable safe mode via:")
    print("  1. Command line: cqlsh --safe-mode <host>")
    print("  2. Config file (~/.cassandra/cqlshrc):")
    print("     [ui]")
    print("     safe_mode = true")
    print()
    print("Note: Safe mode is disabled by default for backward compatibility.")
    print("      In non-TTY mode (scripts/pipes), prompts are automatically skipped.")
    print()


if __name__ == '__main__':
    try:
        simulate_interactive_session()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
        sys.exit(0)
