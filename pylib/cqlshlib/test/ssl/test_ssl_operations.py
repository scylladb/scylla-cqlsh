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
SSL/TLS with CQL operations tests.

Tests SSL with various CQL operations:
- SELECT, INSERT, UPDATE, DELETE
- DDL operations (CREATE TABLE, ALTER, DROP)
- COPY FROM/TO commands
- Batch operations
- Large result sets
"""

import pytest
import ssl
import tempfile
import csv


class TestSSLWithBasicOperations:
    """Test SSL with basic CQL operations."""
    
    def test_select_over_ssl(self, scylla_ssl_container):
        """Test SELECT query over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # SELECT from system table
            result = session.execute("SELECT * FROM system.local")
            rows = list(result)
            
            assert len(rows) > 0
            assert rows[0].cluster_name is not None
        finally:
            cluster.shutdown()
    
    def test_insert_over_ssl(self, scylla_ssl_container):
        """Test INSERT operation over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Create keyspace and table
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_ops
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_ops")
            session.execute("""
                CREATE TABLE IF NOT EXISTS test_insert (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            
            # INSERT data
            session.execute("INSERT INTO test_insert (id, value) VALUES (1, 'test_value')")
            
            # Verify INSERT worked
            result = session.execute("SELECT * FROM test_insert WHERE id = 1")
            rows = list(result)
            
            assert len(rows) == 1
            assert rows[0].value == 'test_value'
            
            # Cleanup
            session.execute("DROP TABLE test_insert")
            session.execute("DROP KEYSPACE test_ssl_ops")
        finally:
            cluster.shutdown()
    
    def test_update_over_ssl(self, scylla_ssl_container):
        """Test UPDATE operation over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Setup
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_ops
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_ops")
            session.execute("""
                CREATE TABLE IF NOT EXISTS test_update (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            session.execute("INSERT INTO test_update (id, value) VALUES (1, 'original')")
            
            # UPDATE data
            session.execute("UPDATE test_update SET value = 'updated' WHERE id = 1")
            
            # Verify UPDATE worked
            result = session.execute("SELECT value FROM test_update WHERE id = 1")
            rows = list(result)
            
            assert len(rows) == 1
            assert rows[0].value == 'updated'
            
            # Cleanup
            session.execute("DROP TABLE test_update")
            session.execute("DROP KEYSPACE test_ssl_ops")
        finally:
            cluster.shutdown()
    
    def test_delete_over_ssl(self, scylla_ssl_container):
        """Test DELETE operation over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Setup
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_ops
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_ops")
            session.execute("""
                CREATE TABLE IF NOT EXISTS test_delete (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            session.execute("INSERT INTO test_delete (id, value) VALUES (1, 'to_delete')")
            
            # DELETE data
            session.execute("DELETE FROM test_delete WHERE id = 1")
            
            # Verify DELETE worked
            result = session.execute("SELECT * FROM test_delete WHERE id = 1")
            rows = list(result)
            
            assert len(rows) == 0
            
            # Cleanup
            session.execute("DROP TABLE test_delete")
            session.execute("DROP KEYSPACE test_ssl_ops")
        finally:
            cluster.shutdown()


class TestSSLWithDDL:
    """Test SSL with DDL operations."""
    
    def test_create_table_over_ssl(self, scylla_ssl_container):
        """Test CREATE TABLE over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # CREATE KEYSPACE
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_ddl
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_ddl")
            
            # CREATE TABLE
            session.execute("""
                CREATE TABLE test_table (
                    id int PRIMARY KEY,
                    name text,
                    created_at timestamp
                )
            """)
            
            # Verify table was created
            result = session.execute("""
                SELECT table_name FROM system_schema.tables
                WHERE keyspace_name = 'test_ssl_ddl' AND table_name = 'test_table'
            """)
            rows = list(result)
            
            assert len(rows) == 1
            
            # Cleanup
            session.execute("DROP TABLE test_table")
            session.execute("DROP KEYSPACE test_ssl_ddl")
        finally:
            cluster.shutdown()
    
    def test_alter_table_over_ssl(self, scylla_ssl_container):
        """Test ALTER TABLE over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Setup
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_ddl
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_ddl")
            session.execute("""
                CREATE TABLE test_alter (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            
            # ALTER TABLE - add column
            session.execute("ALTER TABLE test_alter ADD new_column int")
            
            # Verify column was added
            result = session.execute("""
                SELECT column_name FROM system_schema.columns
                WHERE keyspace_name = 'test_ssl_ddl' AND table_name = 'test_alter'
                AND column_name = 'new_column'
            """)
            rows = list(result)
            
            assert len(rows) == 1
            
            # Cleanup
            session.execute("DROP TABLE test_alter")
            session.execute("DROP KEYSPACE test_ssl_ddl")
        finally:
            cluster.shutdown()
    
    def test_drop_table_over_ssl(self, scylla_ssl_container):
        """Test DROP TABLE over SSL connection."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Setup
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_ddl
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_ddl")
            session.execute("""
                CREATE TABLE test_drop (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            
            # DROP TABLE
            session.execute("DROP TABLE test_drop")
            
            # Verify table was dropped
            result = session.execute("""
                SELECT table_name FROM system_schema.tables
                WHERE keyspace_name = 'test_ssl_ddl' AND table_name = 'test_drop'
            """)
            rows = list(result)
            
            assert len(rows) == 0
            
            # Cleanup
            session.execute("DROP KEYSPACE test_ssl_ddl")
        finally:
            cluster.shutdown()


class TestSSLWithCopyCommand:
    """Test SSL with COPY FROM/TO commands."""
    
    def test_copy_to_over_ssl(self, scylla_ssl_container):
        """Test COPY TO command over SSL connection (via cqlsh)."""
        import subprocess
        from pathlib import Path
        import os
        
        cqlsh_path = Path(__file__).parent.parent.parent.parent.parent / 'bin' / 'cqlsh.py'
        
        # Create test data
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        from cassandra.cluster import Cluster
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_copy
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_copy")
            session.execute("""
                CREATE TABLE test_copy_to (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            session.execute("INSERT INTO test_copy_to (id, value) VALUES (1, 'test1')")
            session.execute("INSERT INTO test_copy_to (id, value) VALUES (2, 'test2')")
        finally:
            cluster.shutdown()
        
        # Use COPY TO command via cqlsh
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as output_file:
            output_path = output_file.name
        
        try:
            env = os.environ.copy()
            env['SSL_CERTFILE'] = scylla_ssl_container.ssl_certificates['ca_cert']
            env['SSL_VALIDATE'] = 'false'
            
            result = subprocess.run([
                'python3', str(cqlsh_path),
                scylla_ssl_container.host,
                str(scylla_ssl_container.port),
                '--ssl',
                '-e', f"COPY test_ssl_copy.test_copy_to TO '{output_path}';"
            ], capture_output=True, text=True, env=env, timeout=30)
            
            # Check that COPY TO worked
            with open(output_path, 'r') as f:
                lines = f.readlines()
                assert len(lines) >= 2  # Should have at least 2 data rows
        finally:
            # Cleanup
            if os.path.exists(output_path):
                os.unlink(output_path)
            
            cluster = Cluster(
                [scylla_ssl_container.host],
                port=scylla_ssl_container.port,
                ssl_context=ssl_context
            )
            try:
                session = cluster.connect()
                session.execute("DROP KEYSPACE test_ssl_copy")
            finally:
                cluster.shutdown()


class TestSSLWithLargeData:
    """Test SSL with large datasets."""
    
    def test_large_result_set_over_ssl(self, scylla_ssl_container):
        """Test fetching large result sets over SSL."""
        from cassandra.cluster import Cluster
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Setup
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_large
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_large")
            session.execute("""
                CREATE TABLE test_large (
                    id int PRIMARY KEY,
                    data text
                )
            """)
            
            # Insert multiple rows
            for i in range(100):
                session.execute(f"INSERT INTO test_large (id, data) VALUES ({i}, 'data_{i}')")
            
            # SELECT all rows
            result = session.execute("SELECT * FROM test_large")
            rows = list(result)
            
            assert len(rows) == 100
            
            # Cleanup
            session.execute("DROP TABLE test_large")
            session.execute("DROP KEYSPACE test_ssl_large")
        finally:
            cluster.shutdown()
    
    def test_batch_operations_over_ssl(self, scylla_ssl_container):
        """Test batch operations over SSL."""
        from cassandra.cluster import Cluster
        from cassandra.query import BatchStatement
        
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Setup
            session.execute("""
                CREATE KEYSPACE IF NOT EXISTS test_ssl_batch
                WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
            """)
            session.execute("USE test_ssl_batch")
            session.execute("""
                CREATE TABLE test_batch (
                    id int PRIMARY KEY,
                    value text
                )
            """)
            
            # Execute batch
            batch = BatchStatement()
            insert_stmt = session.prepare("INSERT INTO test_batch (id, value) VALUES (?, ?)")
            
            for i in range(10):
                batch.add(insert_stmt, (i, f'batch_value_{i}'))
            
            session.execute(batch)
            
            # Verify batch worked
            result = session.execute("SELECT COUNT(*) FROM test_batch")
            count = list(result)[0][0]
            
            assert count == 10
            
            # Cleanup
            session.execute("DROP TABLE test_batch")
            session.execute("DROP KEYSPACE test_ssl_batch")
        finally:
            cluster.shutdown()

        """Test COPY FROM command over SSL connection."""
        # TODO: Implement - important as COPY creates additional connections
        pass
    
    def test_copy_to_over_ssl(self, scylla_ssl_container):
        """Test COPY TO command over SSL connection."""
        # TODO: Implement
        pass


@pytest.mark.skip(reason="Requires SSL-enabled container")
class TestSSLWithLargeData:
    """Test SSL with large datasets."""
    
    def test_large_result_set_over_ssl(self, scylla_ssl_container):
        """Test fetching large result sets over SSL."""
        # TODO: Implement
        pass
    
    def test_batch_operations_over_ssl(self, scylla_ssl_container):
        """Test batch operations over SSL."""
        # TODO: Implement
        pass
