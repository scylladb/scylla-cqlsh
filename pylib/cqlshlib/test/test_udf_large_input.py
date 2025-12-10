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
"""

import time
import pytest
from cassandra import InvalidRequest

from .basecase import BaseTestCase, cqlshlog
from .cassconnect import (cassandra_cursor, create_db, get_keyspace,
                          quote_name, remove_db, testcall_cqlsh)


class TestUDFLargeInput(BaseTestCase):
    """Test for UDF insertion with large input to reproduce performance issues."""

    @classmethod
    def setUpClass(cls):
        """Set up test database and enable UDF."""
        create_db()
        cls.keyspace = get_keyspace()
        
        # Check if we're running against Scylla
        with cassandra_cursor(ks=None) as curs:
            try:
                result = curs.execute("SELECT * FROM system_schema.scylla_tables LIMIT 1;")
                cls.is_scylla = len(result.all()) == 1
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

    def _generate_large_wasm_blob(self, size_mb=1):
        """
        Generate a large blob of data to simulate a WASM UDF body.
        
        Args:
            size_mb: Size in megabytes for the generated blob
            
        Returns:
            A hex string representing the blob
        """
        # Generate a repeating pattern to simulate WASM bytecode
        # Using hex representation as WASM is binary data
        base_pattern = "0061736d01000000"  # WASM magic number and version
        # Repeat the pattern to reach desired size
        size_bytes = size_mb * 1024 * 1024
        hex_chars_needed = size_bytes * 2  # 2 hex chars per byte
        repeats = hex_chars_needed // len(base_pattern) + 1
        blob_hex = (base_pattern * repeats)[:hex_chars_needed]
        return blob_hex

    def test_large_udf_insertion_via_cqlsh(self):
        """
        Test inserting a large UDF (>1MB) via cqlsh to measure performance.
        
        This test creates a CREATE FUNCTION statement with a large WASM-like blob
        and measures how long it takes cqlsh to process it.
        """
        # Generate a 1MB blob for the UDF body
        large_blob = self._generate_large_wasm_blob(size_mb=1)
        blob_size_mb = len(large_blob) / (2 * 1024 * 1024)  # Convert hex chars to MB
        
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
            cqlshlog.info(f"cqlsh output: {output[:500]}")  # Log first 500 chars
            
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
