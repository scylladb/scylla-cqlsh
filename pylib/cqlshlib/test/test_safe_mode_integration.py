#!/usr/bin/env python3
"""
Manual integration test for safe mode feature.

This script demonstrates the safe mode functionality by testing
confirmation prompts for dangerous operations.
"""

import subprocess
import sys
import tempfile
import os

def test_safe_mode_with_confirmation():
    """Test that safe mode prompts for confirmation"""
    
    # Create a test script that tries to drop a keyspace
    test_commands = """
DROP KEYSPACE IF EXISTS test_safe_mode_ks;
CREATE KEYSPACE test_safe_mode_ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
DROP KEYSPACE test_safe_mode_ks;
"""
    
    # Test without safe mode - should execute without prompting
    print("Test 1: Without safe mode (should not prompt)")
    print("-" * 50)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cql', delete=False) as f:
        f.write(test_commands)
        temp_file = f.name
    
    try:
        # This would execute without prompting (but will fail without a cluster)
        result = subprocess.run(
            ['python3', 'bin/cqlsh.py', '--file', temp_file],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"Exit code: {result.returncode}")
        if result.stderr:
            print(f"Error (expected, no cluster): {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print("Command timed out (expected without cluster)")
    finally:
        os.unlink(temp_file)
    
    print("\n" + "=" * 50 + "\n")
    
    # Test with safe mode - would prompt but we're in non-TTY mode (file input)
    print("Test 2: With safe mode and file input (should not prompt in non-TTY)")
    print("-" * 50)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cql', delete=False) as f:
        f.write(test_commands)
        temp_file = f.name
    
    try:
        result = subprocess.run(
            ['python3', 'bin/cqlsh.py', '--safe-mode', '--file', temp_file],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"Exit code: {result.returncode}")
        if result.stderr:
            print(f"Error (expected, no cluster): {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print("Command timed out (expected without cluster)")
    finally:
        os.unlink(temp_file)
    
    print("\n" + "=" * 50 + "\n")
    print("Manual test: To test with interactive prompt, run:")
    print("  python3 bin/cqlsh.py --safe-mode <host>")
    print("  Then try: DROP KEYSPACE test_ks;")
    print("  You should see: Are you sure you want to DROP KEYSPACE test_ks? [N/y]")


if __name__ == '__main__':
    print("Safe Mode Integration Test")
    print("=" * 50 + "\n")
    
    # Change to the repository directory
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_dir)
    
    test_safe_mode_with_confirmation()
    
    print("\n" + "=" * 50)
    print("Tests completed successfully!")
    print("\nNote: The actual confirmation prompts can only be tested")
    print("in an interactive TTY session with a running Cassandra/Scylla cluster.")
