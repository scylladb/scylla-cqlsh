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
SSL/TLS utilities for integration testing.

This module provides utilities for:
- Generating test SSL certificates
- Managing SSL test fixtures
- Configuring cqlsh for SSL connections
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict


def generate_ssl_certificates(output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Generate SSL/TLS certificates for testing using OpenSSL command-line tool.
    
    Creates:
    - CA certificate and private key
    - Server certificate and private key (signed by CA)
    - Client certificate and private key (signed by CA, for mutual TLS)
    
    Args:
        output_dir: Directory to store certificates. If None, creates a temp directory.
    
    Returns:
        Dictionary with paths to generated certificates:
        {
            'ca_cert': 'path/to/ca-cert.pem',
            'ca_key': 'path/to/ca-key.pem',
            'server_cert': 'path/to/server-cert.pem',
            'server_key': 'path/to/server-key.pem',
            'client_cert': 'path/to/client-cert.pem',
            'client_key': 'path/to/client-key.pem',
            'cert_dir': 'path/to/cert/directory'
        }
    
    Note:
        These certificates are for TESTING ONLY and should never be used in production.
        They are self-signed and use weak security parameters for simplicity.
    """
    import subprocess
    
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix='cqlsh_ssl_test_')
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    cert_dir = Path(output_dir)
    
    # Generate CA certificate
    subprocess.run([
        'openssl', 'req', '-new', '-x509', '-nodes', '-days', '365',
        '-keyout', str(cert_dir / 'ca-key.pem'),
        '-out', str(cert_dir / 'ca-cert.pem'),
        '-subj', '/CN=Test CA/O=ScyllaDB Testing/C=US'
    ], check=True, capture_output=True)
    
    # Generate server certificate
    subprocess.run([
        'openssl', 'req', '-new', '-nodes', '-days', '365',
        '-keyout', str(cert_dir / 'server-key.pem'),
        '-out', str(cert_dir / 'server-req.pem'),
        '-subj', '/CN=localhost/O=ScyllaDB Testing/C=US'
    ], check=True, capture_output=True)
    
    subprocess.run([
        'openssl', 'x509', '-req',
        '-in', str(cert_dir / 'server-req.pem'),
        '-CA', str(cert_dir / 'ca-cert.pem'),
        '-CAkey', str(cert_dir / 'ca-key.pem'),
        '-CAcreateserial', '-days', '365',
        '-out', str(cert_dir / 'server-cert.pem')
    ], check=True, capture_output=True)
    
    # Generate client certificate
    subprocess.run([
        'openssl', 'req', '-new', '-nodes', '-days', '365',
        '-keyout', str(cert_dir / 'client-key.pem'),
        '-out', str(cert_dir / 'client-req.pem'),
        '-subj', '/CN=test-client/O=ScyllaDB Testing/C=US'
    ], check=True, capture_output=True)
    
    subprocess.run([
        'openssl', 'x509', '-req',
        '-in', str(cert_dir / 'client-req.pem'),
        '-CA', str(cert_dir / 'ca-cert.pem'),
        '-CAkey', str(cert_dir / 'ca-key.pem'),
        '-CAcreateserial', '-days', '365',
        '-out', str(cert_dir / 'client-cert.pem')
    ], check=True, capture_output=True)
    
    # Clean up CSR files
    (cert_dir / 'server-req.pem').unlink()
    (cert_dir / 'client-req.pem').unlink()
    if (cert_dir / 'ca-cert.srl').exists():
        (cert_dir / 'ca-cert.srl').unlink()
    
    # Set permissions
    os.chmod(cert_dir / 'ca-key.pem', 0o600)
    os.chmod(cert_dir / 'server-key.pem', 0o600)
    os.chmod(cert_dir / 'client-key.pem', 0o600)
    
    return {
        'ca_cert': str(cert_dir / 'ca-cert.pem'),
        'ca_key': str(cert_dir / 'ca-key.pem'),
        'server_cert': str(cert_dir / 'server-cert.pem'),
        'server_key': str(cert_dir / 'server-key.pem'),
        'client_cert': str(cert_dir / 'client-cert.pem'),
        'client_key': str(cert_dir / 'client-key.pem'),
        'cert_dir': str(cert_dir)
    }


def create_cqlshrc_ssl_config(cert_paths: Dict[str, str], 
                              output_file: Optional[str] = None,
                              validate: bool = True,
                              check_hostname: bool = False,
                              require_client_auth: bool = False) -> str:
    """
    Create a cqlshrc configuration file with SSL settings.
    
    Args:
        cert_paths: Dictionary with certificate paths (from generate_ssl_certificates)
        output_file: Path to write cqlshrc. If None, creates temp file.
        validate: Enable certificate validation
        check_hostname: Enable hostname verification
        require_client_auth: Include client certificate configuration
    
    Returns:
        Path to the created cqlshrc file
    """
    if output_file is None:
        fd, output_file = tempfile.mkstemp(prefix='cqlshrc_ssl_', suffix='.conf')
        os.close(fd)
    
    config_content = """[connection]
ssl = true

[ssl]
validate = {validate}
check_hostname = {check_hostname}
certfile = {ca_cert}
""".format(
        validate='true' if validate else 'false',
        check_hostname='true' if check_hostname else 'false',
        ca_cert=cert_paths['ca_cert']
    )
    
    if require_client_auth:
        config_content += """userkey = {client_key}
usercert = {client_cert}
""".format(
            client_key=cert_paths['client_key'],
            client_cert=cert_paths['client_cert']
        )
    
    with open(output_file, 'w') as f:
        f.write(config_content)
    
    return output_file


def cleanup_ssl_files(cert_dir: str):
    """
    Clean up generated SSL certificates and configuration files.
    
    Args:
        cert_dir: Directory containing certificates to remove
    """
    if os.path.exists(cert_dir):
        shutil.rmtree(cert_dir)


class SSLTestContext:
    """
    Context manager for SSL test setup and cleanup.
    
    Usage:
        with SSLTestContext() as ssl_ctx:
            # ssl_ctx.cert_paths contains paths to certificates
            # ssl_ctx.cqlshrc_path contains path to cqlshrc config
            run_ssl_test(ssl_ctx)
        # Cleanup happens automatically
    """
    
    def __init__(self, validate: bool = True, 
                 check_hostname: bool = False,
                 require_client_auth: bool = False):
        """
        Initialize SSL test context.
        
        Args:
            validate: Enable certificate validation
            check_hostname: Enable hostname verification
            require_client_auth: Include client certificate configuration
        """
        self.validate = validate
        self.check_hostname = check_hostname
        self.require_client_auth = require_client_auth
        self.cert_paths = None
        self.cqlshrc_path = None
        self._temp_dirs = []
    
    def __enter__(self):
        """Set up SSL certificates and configuration."""
        self.cert_paths = generate_ssl_certificates()
        self._temp_dirs.append(self.cert_paths['cert_dir'])
        
        # Create cqlshrc in a temp file (not in a directory we need to track)
        # The file is created by tempfile.mkstemp which creates it in the system temp dir
        self.cqlshrc_path = create_cqlshrc_ssl_config(
            self.cert_paths,
            validate=self.validate,
            check_hostname=self.check_hostname,
            require_client_auth=self.require_client_auth
        )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up SSL certificates and configuration."""
        if self.cqlshrc_path and os.path.exists(self.cqlshrc_path):
            os.unlink(self.cqlshrc_path)
        
        for temp_dir in self._temp_dirs:
            cleanup_ssl_files(temp_dir)
        
        return False


def get_ssl_env_vars(cert_paths: Dict[str, str],
                    validate: bool = True,
                    require_client_auth: bool = False) -> Dict[str, str]:
    """
    Get environment variables for SSL configuration.
    
    This is an alternative to using a cqlshrc file.
    
    Args:
        cert_paths: Dictionary with certificate paths
        validate: Enable certificate validation
        require_client_auth: Include client certificate configuration
    
    Returns:
        Dictionary of environment variables to set
    """
    env_vars = {
        'SSL_VALIDATE': 'true' if validate else 'false',
        'SSL_CERTFILE': cert_paths['ca_cert']
    }
    
    if require_client_auth:
        env_vars['SSL_USERCERT'] = cert_paths['client_cert']
        env_vars['SSL_USERKEY'] = cert_paths['client_key']
    
    return env_vars
