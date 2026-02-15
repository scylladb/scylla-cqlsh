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
Mutual TLS (client certificate authentication) tests.

Tests client certificate authentication scenarios:
- Client certificate required
- Client certificate optional
- Client certificate validation
- Missing client certificate handling
"""

import pytest
import ssl


class TestClientCertificateAuth:
    """Client certificate authentication (mutual TLS) tests."""
    
    def test_client_cert_required_with_valid_cert(self, scylla_ssl_container_mtls):
        """Test connection with client certificate when required."""
        from cassandra.cluster import Cluster
        
        # Create SSL context with client certificate
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(scylla_ssl_container_mtls.ssl_certificates['ca_cert'])
        
        # Load client certificate and key
        ssl_context.load_cert_chain(
            certfile=scylla_ssl_container_mtls.ssl_certificates['client_cert'],
            keyfile=scylla_ssl_container_mtls.ssl_certificates['client_key']
        )
        
        # Connect with client certificate
        cluster = Cluster(
            [scylla_ssl_container_mtls.host],
            port=scylla_ssl_container_mtls.port,
            ssl_context=ssl_context
        )
        
        try:
            session = cluster.connect()
            
            # Verify connection works
            result = session.execute("SELECT * FROM system.local")
            assert result is not None
            assert len(list(result)) > 0
        finally:
            cluster.shutdown()
    
    def test_client_cert_required_without_cert(self, scylla_ssl_container_mtls):
        """Test that connection fails without client cert when required."""
        from cassandra.cluster import Cluster, NoHostAvailable
        
        # Create SSL context WITHOUT client certificate
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations(scylla_ssl_container_mtls.ssl_certificates['ca_cert'])
        # Note: NOT loading client certificate
        
        # Try to connect - should fail because server requires client cert
        cluster = Cluster(
            [scylla_ssl_container_mtls.host],
            port=scylla_ssl_container_mtls.port,
            ssl_context=ssl_context
        )
        
        try:
            with pytest.raises((NoHostAvailable, ssl.SSLError, Exception)):
                session = cluster.connect()
                session.execute("SELECT * FROM system.local")
        finally:
            cluster.shutdown()
    
    def test_client_cert_optional(self, scylla_ssl_container):
        """Test connection with and without client cert when optional."""
        from cassandra.cluster import Cluster
        
        # First, connect WITHOUT client certificate (should work when optional)
        ssl_context_no_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context_no_client.check_hostname = False
        ssl_context_no_client.verify_mode = ssl.CERT_REQUIRED
        ssl_context_no_client.load_verify_locations(scylla_ssl_container.ssl_certificates['ca_cert'])
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context_no_client
        )
        
        try:
            session = cluster.connect()
            result = session.execute("SELECT * FROM system.local")
            assert result is not None
        finally:
            cluster.shutdown()
        
        # Second, connect WITH client certificate (should also work)
        ssl_context_with_client = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context_with_client.check_hostname = False
        ssl_context_with_client.verify_mode = ssl.CERT_REQUIRED
        ssl_context_with_client.load_verify_locations(scylla_ssl_container.ssl_certificates['ca_cert'])
        ssl_context_with_client.load_cert_chain(
            certfile=scylla_ssl_container.ssl_certificates['client_cert'],
            keyfile=scylla_ssl_container.ssl_certificates['client_key']
        )
        
        cluster = Cluster(
            [scylla_ssl_container.host],
            port=scylla_ssl_container.port,
            ssl_context=ssl_context_with_client
        )
        
        try:
            session = cluster.connect()
            result = session.execute("SELECT * FROM system.local")
            assert result is not None
        finally:
            cluster.shutdown()
    
    def test_invalid_client_cert_rejected(self, scylla_ssl_container_mtls):
        """Test that invalid client certificates are rejected."""
        from cassandra.cluster import Cluster, NoHostAvailable
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ssl_utils import generate_ssl_certificates, cleanup_ssl_files
        
        wrong_certs = None
        try:
            # Generate different client certificate (signed by different CA)
            wrong_certs = generate_ssl_certificates()
            
            # Create SSL context with WRONG client certificate
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            # Load correct CA for server validation
            ssl_context.load_verify_locations(scylla_ssl_container_mtls.ssl_certificates['ca_cert'])
            # Load WRONG client certificate
            ssl_context.load_cert_chain(
                certfile=wrong_certs['client_cert'],
                keyfile=wrong_certs['client_key']
            )
            
            # Try to connect - should fail
            cluster = Cluster(
                [scylla_ssl_container_mtls.host],
                port=scylla_ssl_container_mtls.port,
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


class TestClientCertificateValidation:
    """Client certificate validation tests."""
    
    def test_client_cert_signed_by_wrong_ca(self, scylla_ssl_container_mtls):
        """Test that client cert signed by wrong CA is rejected."""
        from cassandra.cluster import Cluster, NoHostAvailable
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from ssl_utils import generate_ssl_certificates, cleanup_ssl_files
        
        wrong_certs = None
        try:
            # Generate certificates with a completely different CA
            wrong_certs = generate_ssl_certificates()
            
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.load_verify_locations(scylla_ssl_container_mtls.ssl_certificates['ca_cert'])
            ssl_context.load_cert_chain(
                certfile=wrong_certs['client_cert'],
                keyfile=wrong_certs['client_key']
            )
            
            cluster = Cluster(
                [scylla_ssl_container_mtls.host],
                port=scylla_ssl_container_mtls.port,
                ssl_context=ssl_context
            )
            
            try:
                # Should fail - client cert not signed by trusted CA
                with pytest.raises((NoHostAvailable, ssl.SSLError, Exception)):
                    session = cluster.connect()
                    session.execute("SELECT * FROM system.local")
            finally:
                cluster.shutdown()
        finally:
            if wrong_certs:
                cleanup_ssl_files(wrong_certs['cert_dir'])
    
    def test_expired_client_cert_rejected(self, scylla_ssl_container_mtls):
        """Test that expired client certificates are rejected."""
        # Note: Creating truly expired certificates requires time manipulation
        # or using cryptography library to create certs with past dates
        # This is a simplified test that would need enhancement for full coverage
        pytest.skip("Expired certificate testing requires custom cert generation with past dates")

