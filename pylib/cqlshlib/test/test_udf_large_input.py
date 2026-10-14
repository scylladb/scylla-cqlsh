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
Integration test for reproducing slow performance when inserting large UDF (WASM) via cqlsh.

This test is a reproducer for the issue where cqlsh takes a very long time (e.g., 2 hours)
to insert a UDF with large input (>1MB), while the Python driver does it quickly.

## Running the test:

To run this test with UDF enabled in Scylla, start a Scylla container with UDF configuration:

    # Create a scylla.yaml with UDF enabled
    echo "enable_user_defined_functions: true" > /tmp/scylla.yaml
    echo "experimental_features:" >> /tmp/scylla.yaml
    echo "  - udf" >> /tmp/scylla.yaml
    
    # Start Scylla with custom config
    docker run -d --name scylla-test \\
      -v /tmp/scylla.yaml:/etc/scylla/scylla.yaml \\
      scylladb/scylla:latest --cluster-name test
    
    # Wait for Scylla to be ready and run the test
    export DOCKER_ID=$(docker ps --filter "name=scylla-test" -q)
    export CQL_TEST_HOST=$(docker inspect --format='{{ .NetworkSettings.IPAddress }}' ${DOCKER_ID})
    while ! nc -z ${CQL_TEST_HOST} 9042; do sleep 0.5; done
    pytest pylib/cqlshlib/test/test_udf_large_input.py -v -s

## Expected behavior:

When UDF is NOT enabled (default):
- Test will fail with "User defined functions are disabled" error
- Execution time will be fast (<1 second)
- Test passes (as it expects either success or error)

When UDF IS enabled and performance issue exists:
- Test will take a very long time to execute (potentially hours)
- Test will fail with timeout assertion if execution takes >60 seconds
- This demonstrates the performance issue

When UDF IS enabled and performance issue is fixed:
- Test will execute quickly (<60 seconds)
- Function will be created successfully
- Test passes

Note: WASM UDF support may vary by Scylla version. Check the Scylla documentation
at https://opensource.docs.scylladb.com/master/cql/wasm.html for details.
"""

import time
import os
import pytest
from cassandra import InvalidRequest

from .basecase import BaseTestCase, cqlshlog, test_dir
from .cassconnect import (cassandra_cursor, create_db, get_keyspace,
                          quote_name, remove_db, testcall_cqlsh, split_cql_commands)
from cqlshlib.cql3handling import CqlRuleSet


class TestUDFLargeInput(BaseTestCase):
    """Test for UDF insertion with large input to reproduce performance issues."""
    
    # Maximum characters of cqlsh output to log (to avoid overwhelming logs)
    MAX_LOG_OUTPUT_CHARS = 500

    @classmethod
    def setUpClass(cls):
        """Set up test database and enable UDF."""
        create_db()
        cls.keyspace = get_keyspace()
        
        # Check if we're running against Scylla
        with cassandra_cursor(ks=None) as curs:
            try:
                result = curs.execute("SELECT * FROM system_schema.scylla_tables LIMIT 1;")
                cls.is_scylla = len(result.all()) >= 1
            except InvalidRequest:
                cls.is_scylla = False
        
        # Enable UDF if running against Scylla
        if cls.is_scylla:
            try:
                with cassandra_cursor(ks=None) as curs:
                    curs.execute("UPDATE system.config SET value = 'true' WHERE name = 'enable_user_defined_functions';")
                    cqlshlog.info("Enabled user-defined functions")
            except Exception as e:
                cqlshlog.warning(f"Could not enable UDF: {e}")

    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        remove_db()

    def _load_real_wasm_udf(self):
        """
        Load the real WASM UDF from the udf_commas.cql file.
        
        This file contains an actual WASM function that was reported to cause
        performance issues in cqlsh.
        
        Returns:
            The CQL statement as a string
        """
        udf_file = os.path.join(test_dir, 'udf_commas.cql')
        with open(udf_file, 'r') as f:
            content = f.read()
        
        cqlshlog.info(f"Loaded real WASM UDF file: {len(content)} chars ({len(content) / (1024 * 1024):.2f} MB)")
        return content

    def _generate_large_wasm_blob(self, size_mb=1):
        """
        Generate a large blob of actual WASM bytecode for a UDF body.
        
        This uses a minimal valid WASM module (41 bytes) that exports an "add" function
        which takes two i32 parameters and returns their sum. The module is repeated
        to reach the desired size.
        
        Args:
            size_mb: Size in megabytes for the generated blob
            
        Returns:
            A hex string representing the WASM bytecode
        """
        # Minimal valid WASM module (41 bytes) with an exported "add" function
        # Module structure:
        # - Magic number and version: \0asm version 1
        # - Type section: func(i32, i32) -> i32
        # - Function section: declares 1 function of type 0
        # - Export section: exports function 0 as "add"
        # - Code section: local.get 0, local.get 1, i32.add, end
        minimal_wasm_module = "0061736d0100000001070160027f7f017f030201000707010361646400000a09010700200020016a0b"
        
        # Calculate how many times to repeat the module to reach desired size
        size_bytes = size_mb * 1024 * 1024
        # 2 hex characters per byte
        hex_chars_needed = size_bytes * 2
        repeats = hex_chars_needed // len(minimal_wasm_module) + 1
        blob_hex = (minimal_wasm_module * repeats)[:hex_chars_needed]
        return blob_hex

    def test_large_udf_insertion_via_cqlsh(self):
        """
        Test inserting a large UDF (>1MB) via cqlsh to measure performance.
        
        This test creates a CREATE FUNCTION statement with a large WASM-like blob
        and measures how long it takes cqlsh to process it.
        """
        # Generate a 1MB blob for the UDF body
        large_blob = self._generate_large_wasm_blob(size_mb=1)
        # 2 hex chars per byte, then convert bytes to MB
        blob_size_mb = len(large_blob) / (2 * 1024 * 1024)
        
        cqlshlog.info(f"Generated blob of size: {blob_size_mb:.2f} MB")
        
        # Create a CREATE FUNCTION statement with the large blob
        # Note: This simulates a WASM UDF as described in Scylla docs
        function_name = "test_large_wasm_func"
        create_function_stmt = f"""
        CREATE FUNCTION {self.keyspace}.{function_name}(val int)
        RETURNS NULL ON NULL INPUT
        RETURNS int
        LANGUAGE wasm
        AS '0x{large_blob}';
        """
        
        cqlshlog.info(f"CQL statement size: {len(create_function_stmt) / (1024 * 1024):.2f} MB")
        
        # Time the execution via cqlsh
        start_time = time.time()
        
        try:
            output, result = testcall_cqlsh(
                input=create_function_stmt,
                keyspace=self.keyspace
            )
            
            elapsed_time = time.time() - start_time
            
            cqlshlog.info(f"cqlsh execution time: {elapsed_time:.2f} seconds")
            cqlshlog.info(f"cqlsh output: {output[:self.MAX_LOG_OUTPUT_CHARS]}")
            
            # The test passes if it completes (even with an error), as we're measuring time
            # In a real scenario, we'd compare with Python driver execution time
            # For now, we just log the execution time for analysis
            
            # Log whether it succeeded or failed
            if result != 0:
                cqlshlog.warning(f"cqlsh returned error code: {result}")
                cqlshlog.warning(f"This may be expected if WASM UDFs are not supported")
            else:
                cqlshlog.info(f"Function created successfully")
                
                # Clean up - drop the function
                try:
                    drop_stmt = f"DROP FUNCTION {self.keyspace}.{function_name};"
                    testcall_cqlsh(input=drop_stmt, keyspace=self.keyspace)
                except Exception as e:
                    cqlshlog.warning(f"Could not drop function: {e}")
            
            # Assert that execution completes in reasonable time (e.g., < 60 seconds)
            # This threshold can be adjusted based on actual performance expectations
            assert elapsed_time < 60, \
                f"cqlsh took too long ({elapsed_time:.2f}s) to process large UDF. " \
                f"Expected < 60 seconds. This reproduces the performance issue."
                
        except Exception as e:
            elapsed_time = time.time() - start_time
            cqlshlog.error(f"Test failed after {elapsed_time:.2f} seconds: {e}")
            raise

    def test_large_udf_insertion_via_driver(self):
        """
        Test inserting a large UDF via Python driver for comparison.
        
        This test creates the same large UDF using the Python driver directly
        to compare performance with cqlsh.
        """
        # Generate a 1MB blob for the UDF body
        large_blob = self._generate_large_wasm_blob(size_mb=1)
        blob_size_mb = len(large_blob) / (2 * 1024 * 1024)
        
        cqlshlog.info(f"Generated blob of size: {blob_size_mb:.2f} MB (driver test)")
        
        function_name = "test_large_wasm_func_driver"
        create_function_stmt = f"""
        CREATE FUNCTION {self.keyspace}.{function_name}(val int)
        RETURNS NULL ON NULL INPUT
        RETURNS int
        LANGUAGE wasm
        AS '0x{large_blob}';
        """
        
        # Time the execution via Python driver
        start_time = time.time()
        
        try:
            with cassandra_cursor(ks=self.keyspace) as curs:
                curs.execute(create_function_stmt)
            
            elapsed_time = time.time() - start_time
            cqlshlog.info(f"Python driver execution time: {elapsed_time:.2f} seconds")
            
            # Clean up - drop the function
            try:
                with cassandra_cursor(ks=self.keyspace) as curs:
                    curs.execute(f"DROP FUNCTION {self.keyspace}.{function_name};")
            except Exception as e:
                cqlshlog.warning(f"Could not drop function: {e}")
            
            # Driver should be much faster
            cqlshlog.info(f"Driver completed in {elapsed_time:.2f} seconds")
            
        except InvalidRequest as e:
            elapsed_time = time.time() - start_time
            cqlshlog.info(f"Driver test completed in {elapsed_time:.2f} seconds with error: {e}")
            # This is expected if WASM UDFs are not supported or UDF is not enabled
            pytest.skip(f"WASM UDF not supported or UDF not enabled: {e}")
        except Exception as e:
            elapsed_time = time.time() - start_time
            cqlshlog.error(f"Driver test failed after {elapsed_time:.2f} seconds: {e}")
            raise

    def test_cql_split_statements_on_real_wasm(self):
        """
        Test that cql_split_statements can handle the real WASM UDF file without errors.
        
        This verifies that the lexer doesn't raise a LexingError on large WASM input
        that contains commas and other special characters.
        """
        # Load the real WASM UDF
        udf_content = self._load_real_wasm_udf()
        
        cqlshlog.info(f"Testing cql_split_statements on {len(udf_content)} chars")
        
        # Try to split statements - this should not raise a LexingError
        start_time = time.time()
        try:
            statements, endtoken_escaped = CqlRuleSet.cql_split_statements(udf_content)
            elapsed_time = time.time() - start_time
            
            cqlshlog.info(f"cql_split_statements completed in {elapsed_time:.2f} seconds")
            cqlshlog.info(f"Found {len(statements)} statements")
            cqlshlog.info(f"Endtoken escaped: {endtoken_escaped}")
            
            # Should successfully parse the statement
            assert len(statements) > 0, "Should have parsed at least one statement"
            
            # Log success
            cqlshlog.info("✓ cql_split_statements successfully parsed real WASM UDF")
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            cqlshlog.error(f"cql_split_statements failed after {elapsed_time:.2f} seconds: {type(e).__name__}: {e}")
            raise

    def test_real_wasm_udf_insertion_via_cqlsh(self):
        """
        Test inserting the real WASM UDF via cqlsh to measure performance.
        
        This uses the actual udf_commas.cql file that was reported to cause
        2-hour execution times in cqlsh.
        """
        # Load the real WASM UDF
        create_function_stmt = self._load_real_wasm_udf()
        
        # Modify the statement to use our test keyspace
        # Replace test_ks with our keyspace
        create_function_stmt = create_function_stmt.replace('test_ks.commas', f'{self.keyspace}.commas')
        
        cqlshlog.info(f"Testing real WASM UDF insertion via cqlsh")
        cqlshlog.info(f"CQL statement size: {len(create_function_stmt) / (1024 * 1024):.2f} MB")
        
        # Time the execution via cqlsh
        start_time = time.time()
        
        try:
            output, result = testcall_cqlsh(
                input=create_function_stmt,
                keyspace=self.keyspace
            )
            
            elapsed_time = time.time() - start_time
            
            cqlshlog.info(f"cqlsh execution time: {elapsed_time:.2f} seconds")
            cqlshlog.info(f"cqlsh output: {output[:self.MAX_LOG_OUTPUT_CHARS]}")
            
            # Log whether it succeeded or failed
            if result != 0:
                cqlshlog.warning(f"cqlsh returned error code: {result}")
                cqlshlog.warning(f"This may be expected if WASM UDFs are not supported")
            else:
                cqlshlog.info(f"Function created successfully")
                
                # Clean up - drop the function
                try:
                    drop_stmt = f"DROP FUNCTION {self.keyspace}.commas;"
                    testcall_cqlsh(input=drop_stmt, keyspace=self.keyspace)
                except Exception as e:
                    cqlshlog.warning(f"Could not drop function: {e}")
            
            # Assert that execution completes in reasonable time
            # The original issue reported 2 hours, so 60 seconds is a reasonable threshold
            assert elapsed_time < 60, \
                f"cqlsh took too long ({elapsed_time:.2f}s) to process real WASM UDF. " \
                f"Expected < 60 seconds. This reproduces the performance issue."
                
        except Exception as e:
            elapsed_time = time.time() - start_time
            cqlshlog.error(f"Test failed after {elapsed_time:.2f} seconds: {e}")
            raise
