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
Basic SSL/TLS connection tests.

Tests basic SSL connectivity to ScyllaDB/Cassandra:
- Connect with SSL enabled
- Connect without certificate validation
- Connect with certificate validation
- Verify SSL connection is actually encrypted
"""

import pytest
import ssl
import socket


class TestBasicSSLConnection:
    """Basic SSL connection tests."""
    
    def test_connect_with_ssl_no_validation(self, scylla_ssl_container):
        """Test connecting with SSL but no certificate validation."""
        from cassandra.cluster import Cluster
        from cassandra import ConsistencyLevel
        
        # Create SSL context without validation
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Connect to ScyllaDB with SSL
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Test basic query
            result = session.execute("SELECT * FROM system.local")
            assert result is not None
            assert len(list(result)) > 0
            
            # Verify we can get cluster name
            row = list(result)[0]
            assert hasattr(row, 'cluster_name') or 'cluster_name' in row._asdict()
        finally:
            cluster.shutdown()
    
    def test_connect_with_ssl_and_validation(self, scylla_ssl_container):
        """Test connecting with SSL and certificate validation enabled."""
        from cassandra.cluster import Cluster
        
        # Create SSL context with validation
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False  # Disable hostname check for self-signed certs
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(scylla_ssl_container.ssl_certificates['ca_cert'])
        
        # Connect to ScyllaDB with SSL validation
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Test basic query
            result = session.execute("SELECT release_version FROM system.local")
            assert result is not None
            
            version = list(result)[0][0]
            assert version is not None
        finally:
            cluster.shutdown()
    
    def test_verify_connection_is_encrypted(self, scylla_ssl_container):
        """Verify that the connection is actually using SSL/TLS."""
        # Test that we can establish an SSL socket connection
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((scylla_ssl_container.host, scylla_ssl_container.port)) as sock:
            with ssl_context.wrap_socket(sock, server_hostname=scylla_ssl_container.host) as ssock:
                # Verify SSL is active
                assert ssock.version() is not None
                cipher = ssock.cipher()
                assert cipher is not None
                assert len(cipher) >= 3  # cipher is a tuple (name, protocol_version, secret_bits)


class TestSSLConnectionErrors:
    """Test SSL connection error handling."""
    
    def test_connection_fails_without_ssl_to_ssl_port(self, scylla_ssl_container):
        """Test that non-SSL connection to SSL port fails appropriately."""
        from cassandra.cluster import Cluster, NoHostAvailable
        
        # Try to connect without SSL to SSL-enabled port
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            # No ssl_context provided
        )
        
        try:
            # This should fail because the server expects SSL
            with pytest.raises((NoHostAvailable, Exception)):
                session = cluster.connect()
                session.execute("SELECT * FROM system.local")
        finally:
            cluster.shutdown()
    
    def test_connection_with_wrong_ca_cert(self, scylla_ssl_container, ssl_certificates):
        """Test that connection fails with wrong CA certificate."""
        from cassandra.cluster import Cluster, NoHostAvailable
        import tempfile
        
        # Generate a different CA certificate
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ssl_utils import generate_ssl_certificates, cleanup_ssl_files
        
        wrong_certs = None
        try:
            # Generate completely different certificates
            wrong_certs = generate_ssl_certificates()
            
            # Create SSL context with wrong CA
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.load_verify_locations(wrong_certs['ca_cert'])
            
            # Try to connect - should fail due to certificate validation
            cluster = Cluster(
                [scylla_ssl_container.host],
                port=scylla_ssl_container.port,
                ssl_context=ssl_context
            )
            
            try:
                with pytest.raises((NoHostAvailable, ssl.SSLError, Exception)):
                    session = cluster.connect()
                    session.execute("SELECT * FROM system.local")
            finally:
                cluster.shutdown()
        finally:
            if wrong_certs:
                cleanup_ssl_files(wrong_certs['cert_dir'])

