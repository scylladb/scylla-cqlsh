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
Tests for SSL/TLS certificate generation and utility functions.

These tests verify the SSL utilities work correctly without requiring
a running database cluster.
"""

import os
import pytest
import subprocess
from pathlib import Path

# Import from parent test directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from ssl_utils import (
    generate_ssl_certificates,
    generate_ssl_certificates_python,
    generate_ssl_certificates_bash,
    SSLTestContext,
    HAS_CRYPTOGRAPHY
)


class TestCertificateGeneration:
    """Test SSL certificate generation functions."""
    
    def test_generate_certificates_creates_all_files(self, ssl_certificates):
        """Test that certificate generation creates all expected files."""
        assert os.path.exists(ssl_certificates['ca_cert'])
        assert os.path.exists(ssl_certificates['ca_key'])
        assert os.path.exists(ssl_certificates['server_cert'])
        assert os.path.exists(ssl_certificates['server_key'])
        assert os.path.exists(ssl_certificates['client_cert'])
        assert os.path.exists(ssl_certificates['client_key'])
        assert os.path.exists(ssl_certificates['cert_dir'])
    
    def test_certificate_permissions(self, ssl_certificates):
        """Test that private keys have restrictive permissions."""
        # Private keys should be 600 (read/write for owner only)
        ca_key_mode = os.stat(ssl_certificates['ca_key']).st_mode & 0o777
        server_key_mode = os.stat(ssl_certificates['server_key']).st_mode & 0o777
        client_key_mode = os.stat(ssl_certificates['client_key']).st_mode & 0o777
        
        assert ca_key_mode == 0o600, f"CA key has wrong permissions: {oct(ca_key_mode)}"
        assert server_key_mode == 0o600, f"Server key has wrong permissions: {oct(server_key_mode)}"
        assert client_key_mode == 0o600, f"Client key has wrong permissions: {oct(client_key_mode)}"
    
    def test_ca_certificate_validity(self, ssl_certificates):
        """Test that CA certificate is valid and well-formed."""
        result = subprocess.run([
            'openssl', 'x509', '-in', ssl_certificates['ca_cert'],
            '-noout', '-subject', '-issuer'
        ], capture_output=True, text=True, check=True)
        
        assert 'Test CA' in result.stdout
        assert 'ScyllaDB Testing' in result.stdout
    
    def test_server_certificate_validity(self, ssl_certificates):
        """Test that server certificate is valid and signed by CA."""
        # Check subject
        result = subprocess.run([
            'openssl', 'x509', '-in', ssl_certificates['server_cert'],
            '-noout', '-subject'
        ], capture_output=True, text=True, check=True)
        
        assert 'localhost' in result.stdout
        
        # Verify signature by CA
        result = subprocess.run([
            'openssl', 'verify',
            '-CAfile', ssl_certificates['ca_cert'],
            ssl_certificates['server_cert']
        ], capture_output=True, text=True)
        
        assert result.returncode == 0, f"Server cert verification failed: {result.stderr}"
        assert 'OK' in result.stdout
    
    def test_client_certificate_validity(self, ssl_certificates):
        """Test that client certificate is valid and signed by CA."""
        # Check subject
        result = subprocess.run([
            'openssl', 'x509', '-in', ssl_certificates['client_cert'],
            '-noout', '-subject'
        ], capture_output=True, text=True, check=True)
        
        assert 'test-client' in result.stdout
        
        # Verify signature by CA
        result = subprocess.run([
            'openssl', 'verify',
            '-CAfile', ssl_certificates['ca_cert'],
            ssl_certificates['client_cert']
        ], capture_output=True, text=True)
        
        assert result.returncode == 0, f"Client cert verification failed: {result.stderr}"
        assert 'OK' in result.stdout


class TestCertificateGenerationMethods:
    """Test different certificate generation methods."""
    
    @pytest.mark.skipif(not HAS_CRYPTOGRAPHY, reason="cryptography package not available")
    def test_generate_certificates_python(self):
        """Test pure Python certificate generation."""
        from ssl_utils import cleanup_ssl_files
        
        cert_paths = None
        try:
            cert_paths = generate_ssl_certificates_python()
            
            # Verify all files exist
            assert os.path.exists(cert_paths['ca_cert'])
            assert os.path.exists(cert_paths['server_cert'])
            assert os.path.exists(cert_paths['client_cert'])
        finally:
            if cert_paths:
                cleanup_ssl_files(cert_paths['cert_dir'])
    
    def test_generate_certificates_bash(self):
        """Test bash script certificate generation."""
        from ssl_utils import cleanup_ssl_files
        
        cert_paths = None
        try:
            cert_paths = generate_ssl_certificates_bash()
            
            # Verify all files exist
            assert os.path.exists(cert_paths['ca_cert'])
            assert os.path.exists(cert_paths['server_cert'])
            assert os.path.exists(cert_paths['client_cert'])
        finally:
            if cert_paths:
                cleanup_ssl_files(cert_paths['cert_dir'])
    
    def test_generate_certificates_auto_method(self):
        """Test auto method selection for certificate generation."""
        from ssl_utils import cleanup_ssl_files
        
        cert_paths = None
        try:
            # Auto should work regardless of cryptography availability
            cert_paths = generate_ssl_certificates(method='auto')
            
            assert os.path.exists(cert_paths['ca_cert'])
            assert os.path.exists(cert_paths['server_cert'])
        finally:
            if cert_paths:
                cleanup_ssl_files(cert_paths['cert_dir'])


class TestSSLTestContext:
    """Test the SSLTestContext context manager."""
    
    def test_ssl_context_manager(self):
        """Test that SSLTestContext properly manages resources."""
        cert_dir = None
        cqlshrc_path = None
        
        with SSLTestContext(validate=True, check_hostname=False) as ssl_ctx:
            # Verify context provides necessary paths
            assert ssl_ctx.cert_paths is not None
            assert ssl_ctx.cqlshrc_path is not None
            
            # Verify files exist during context
            assert os.path.exists(ssl_ctx.cqlshrc_path)
            assert os.path.exists(ssl_ctx.cert_paths['ca_cert'])
            
            cert_dir = ssl_ctx.cert_paths['cert_dir']
            cqlshrc_path = ssl_ctx.cqlshrc_path
        
        # Verify cleanup happened after context
        assert not os.path.exists(cert_dir), "Certificate directory should be cleaned up"
        assert not os.path.exists(cqlshrc_path), "cqlshrc file should be cleaned up"
    
    def test_ssl_context_with_client_auth(self):
        """Test SSLTestContext with client authentication enabled."""
        with SSLTestContext(require_client_auth=True) as ssl_ctx:
            # Read cqlshrc and verify client cert configuration
            with open(ssl_ctx.cqlshrc_path, 'r') as f:
                config = f.read()
            
            assert 'userkey' in config
            assert 'usercert' in config
            assert ssl_ctx.cert_paths['client_key'] in config
            assert ssl_ctx.cert_paths['client_cert'] in config
