# Safe Mode Feature

## Overview

The safe mode feature in CQLsh provides protection against accidental execution of dangerous operations by prompting for user confirmation before executing statements that could result in data loss.

## Dangerous Operations

The following operations are considered dangerous and will trigger a confirmation prompt in safe mode:

- `DROP KEYSPACE` - Removes an entire keyspace and all its data
- `DROP TABLE` / `DROP COLUMNFAMILY` - Removes a table and all its data
- `DROP INDEX` - Removes an index
- `DROP MATERIALIZED VIEW` - Removes a materialized view
- `DROP TYPE` - Removes a user-defined type
- `DROP FUNCTION` - Removes a user-defined function
- `DROP AGGREGATE` - Removes a user-defined aggregate
- `DROP USER` - Removes a user account
- `DROP ROLE` - Removes a role
- `DROP SERVICE_LEVEL` - Removes a service level
- `DROP TRIGGER` - Removes a trigger
- `TRUNCATE` - Removes all data from a table

## Usage

### Command Line

Enable safe mode using the `--safe-mode` command-line option:

```bash
cqlsh --safe-mode
cqlsh --safe-mode hostname
cqlsh --safe-mode hostname 9042
```

### Configuration File

Add the following line to the `[ui]` section of your `.cqlshrc` file:

```ini
[ui]
safe_mode = true
```

Example `.cqlshrc`:

```ini
[ui]
safe_mode = true
color = on
```

## Behavior

### Interactive Mode (TTY)

When safe mode is enabled and you execute a dangerous operation in an interactive session, you will be prompted for confirmation:

```
cqlsh> DROP KEYSPACE test_ks;
Are you sure you want to DROP KEYSPACE test_ks? [N/y] 
```

Valid responses:
- `y` or `yes` (case insensitive) - Proceed with the operation
- `n`, `no`, or just pressing Enter (default) - Cancel the operation
- `Ctrl+C` or `Ctrl+D` - Cancel the operation

### Non-Interactive Mode (Scripts)

When running CQLsh with file input or in non-TTY mode (e.g., piped input), safe mode does not prompt for confirmation and allows operations to proceed. This ensures that scripts continue to work without manual intervention.

```bash
# These commands will execute without prompting
cqlsh --safe-mode --file script.cql
echo "DROP TABLE test_table;" | cqlsh --safe-mode
```

## Default Behavior

Safe mode is **disabled by default** to maintain backward compatibility with existing workflows and scripts. You must explicitly enable it via command-line option or configuration file.

## Examples

### Example 1: Preventing Accidental Keyspace Drop

```
cqlsh> DROP KEYSPACE production_data;
Are you sure you want to DROP KEYSPACE production_data? [N/y] n
Operation cancelled.
cqlsh> 
```

### Example 2: Confirming Table Truncate

```
cqlsh> TRUNCATE TABLE user_sessions;
Are you sure you want to TRUNCATE user_sessions? [N/y] y
cqlsh> 
```

### Example 3: Handling IF EXISTS

Safe mode works with `IF EXISTS` clauses:

```
cqlsh> DROP TABLE IF EXISTS old_table;
Are you sure you want to DROP TABLE old_table? [N/y] 
```

## Testing

Run the unit tests:

```bash
python3 -m unittest pylib/cqlshlib/test/test_safe_mode.py -v
```

Run the demonstration script:

```bash
python3 pylib/cqlshlib/test/demo_safe_mode.py
```

## Implementation Details

The safe mode feature consists of:

1. **Command-line option**: `--safe-mode` flag
2. **Configuration option**: `safe_mode` in `[ui]` section of cqlshrc
3. **Shell attribute**: `self.safe_mode` boolean flag in Shell class
4. **Detection method**: `is_dangerous_statement()` - identifies dangerous operations
5. **Extraction method**: `extract_operation_target()` - extracts target names for better prompts
6. **Prompt method**: `prompt_for_confirmation()` - handles user interaction
7. **Integration**: Modified `perform_statement()` to check and prompt before execution

## Limitations

- The feature detects dangerous operations based on statement patterns (keywords at the beginning of the statement)
- In non-TTY mode, operations always proceed without prompting
- The feature does not prevent data loss from UPDATE or DELETE statements (only DROP and TRUNCATE)

## Future Enhancements

Potential improvements for future versions:

- Pattern matching for destructive UPDATE/DELETE operations (e.g., `DELETE FROM table` without WHERE clause)
- Whitelist/blacklist of keyspaces or tables that always/never prompt
- Logging of dangerous operations
- Integration with audit logging
