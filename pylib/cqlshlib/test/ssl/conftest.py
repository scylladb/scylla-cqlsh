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
Shared pytest fixtures for SSL/TLS integration tests.

This module provides fixtures for:
- SSL certificate generation
- SSL-enabled container management (ScyllaDB, Cassandra)
- SSL configuration helpers
"""

import os
import pytest
from pathlib import Path

# Import SSL utilities from parent test directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from ssl_utils import generate_ssl_certificates, cleanup_ssl_files, SSLTestContext


@pytest.fixture(scope='module')
def ssl_certificates():
    """
    Generate SSL certificates for testing.
    
    This fixture creates a complete SSL certificate chain including:
    - CA certificate and private key
    - Server certificate (signed by CA)
    - Client certificate (signed by CA, for mutual TLS)
    
    Yields:
        dict: Dictionary with paths to all generated certificates
    
    Cleanup:
        Automatically removes all generated certificates after tests complete
    """
    cert_paths = None
    try:
        cert_paths = generate_ssl_certificates()
        yield cert_paths
    finally:
        if cert_paths is not None:
            cleanup_ssl_files(cert_paths['cert_dir'])


@pytest.fixture(scope='module')
def ssl_context():
    """
    SSL test context with certificates and cqlshrc configuration.
    
    Provides a complete SSL test context including certificates
    and pre-configured cqlshrc file.
    
    Yields:
        SSLTestContext: Context with cert_paths and cqlshrc_path
    """
    with SSLTestContext(validate=True, check_hostname=False) as ctx:
        yield ctx


@pytest.fixture(scope='module')
def scylla_ssl_container(ssl_certificates):
    """
    ScyllaDB container with SSL/TLS enabled (using testcontainers).
    
    This fixture:
    1. Starts a ScyllaDB container
    2. Mounts SSL certificates
    3. Configures client encryption
    4. Waits for readiness
    5. Yields connection info
    6. Cleans up automatically
    
    Args:
        ssl_certificates: Fixture providing SSL certificates
    
    Yields:
        Container instance with connection details
    
    Note:
        Requires testcontainers package and Docker
    """
    try:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.waiting_strategies import wait_for_logs
        import time
    except ImportError:
        pytest.skip("testcontainers package not available")
    
    # Prepare SSL configuration
    ssl_config_path = Path(__file__).parent / 'scylla-ssl.yaml'
    
    # Create and configure ScyllaDB container
    # Note: ScyllaDB doesn't have a dedicated testcontainer yet, so we use generic container
    container = DockerContainer("scylladb/scylla:latest")
    
    # Mount SSL certificates
    container.with_volume_mapping(
        ssl_certificates['cert_dir'],
        "/etc/scylla/ssl",
        mode="ro"
    )
    
    # Mount SSL configuration
    container.with_volume_mapping(
        str(ssl_config_path),
        "/etc/scylla/scylla.yaml",
        mode="ro"
    )
    
    # Expose CQL port
    container.with_exposed_ports(9042)
    
    # Start container and wait for it to be ready
    container.start()
    
    try:
        # Wait for ScyllaDB to start (look for ready message in logs)
        # This may take 30-60 seconds for ScyllaDB to initialize
        time.sleep(10)  # Initial wait
        
        # Get container connection info
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9042)
        
        # Create a simple connection info object
        class ConnectionInfo:
            def __init__(self, host, port, ssl_certs):
                self.host = host
                self.port = int(port)
                self.ssl_certificates = ssl_certs
        
        yield ConnectionInfo(host, port, ssl_certificates)
    finally:
        container.stop()


@pytest.fixture(scope='module')
def scylla_ssl_container_mtls(ssl_certificates):
    """
    ScyllaDB container with mutual TLS (client certificate required).
    
    Similar to scylla_ssl_container but requires client certificates.
    
    Args:
        ssl_certificates: Fixture providing SSL certificates
    
    Yields:
        Container instance with connection details
    """
    try:
        from testcontainers.core.container import DockerContainer
        import time
        import tempfile
    except ImportError:
        pytest.skip("testcontainers package not available")
    
    # Create SSL configuration with client auth required
    mtls_config = """
client_encryption_options:
    enabled: true
    certificate: /etc/scylla/ssl/server-cert.pem
    keyfile: /etc/scylla/ssl/server-key.pem
    truststore: /etc/scylla/ssl/ca-cert.pem
    require_client_auth: true
"""
    
    # Write temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(mtls_config)
        mtls_config_path = f.name
    
    try:
        container = DockerContainer("scylladb/scylla:latest")
        
        container.with_volume_mapping(
            ssl_certificates['cert_dir'],
            "/etc/scylla/ssl",
            mode="ro"
        )
        
        container.with_volume_mapping(
            mtls_config_path,
            "/etc/scylla/scylla.yaml",
            mode="ro"
        )
        
        container.with_exposed_ports(9042)
        container.start()
        
        try:
            time.sleep(10)
            
            host = container.get_container_host_ip()
            port = container.get_exposed_port(9042)
            
            class ConnectionInfo:
                def __init__(self, host, port, ssl_certs):
                    self.host = host
                    self.port = int(port)
                    self.ssl_certificates = ssl_certs
                    self.require_client_auth = True
            
            yield ConnectionInfo(host, port, ssl_certificates)
        finally:
            container.stop()
    finally:
        os.unlink(mtls_config_path)


@pytest.fixture(scope='module')
def cassandra_ssl_container(ssl_certificates):
    """
    Cassandra container with SSL/TLS enabled (using testcontainers).
    
    Similar to scylla_ssl_container but for Apache Cassandra.
    
    Args:
        ssl_certificates: Fixture providing SSL certificates
    
    Yields:
        Container instance with connection details
    
    Note:
        Requires testcontainers package and Docker.
        Cassandra SSL configuration is more complex than ScyllaDB.
    """
    pytest.skip("Cassandra SSL configuration pending - requires keystore/truststore setup")
    
    # TODO: Cassandra uses Java keystores (JKS format) instead of PEM files
    # Need to convert PEM certificates to JKS format using keytool
    # from testcontainers.core.container import DockerContainer
    # 
    # Implementation requires:
    # 1. Convert PEM certs to JKS keystore/truststore
    # 2. Configure cassandra.yaml with SSL settings
    # 3. Mount keystores and config to container



@pytest.fixture
def ssl_env_vars(ssl_certificates):
    """
    Environment variables for SSL configuration.
    
    Provides a dictionary of environment variables that can be used
    to configure SSL in cqlsh (alternative to cqlshrc).
    
    Args:
        ssl_certificates: Fixture providing SSL certificates
    
    Returns:
        dict: Environment variables for SSL configuration
    """
    from ssl_utils import get_ssl_env_vars
    
    return get_ssl_env_vars(ssl_certificates, validate=False)


# Configuration for test discovery
def pytest_collection_modifyitems(items):
    """
    Automatically mark all tests in this module with the 'ssl' marker.
    
    This ensures that SSL tests can be easily run or skipped using:
        pytest -m ssl        # Run only SSL tests
        pytest -m "not ssl"  # Skip SSL tests
    """
    for item in items:
        if 'ssl' in str(item.fspath):
            item.add_marker(pytest.mark.ssl)
