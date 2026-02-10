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
    pytest.skip("Testcontainers integration pending - see docs/plans/SSL_TLS_INTEGRATION_TEST_PLAN.md")
    
    # TODO: Implement testcontainers integration
    # from testcontainers.scylla import ScyllaContainer
    #
    # # Create SSL configuration file
    # ssl_config_path = Path(ssl_certificates['cert_dir']) / 'scylla-ssl.yaml'
    # with open(ssl_config_path, 'w') as f:
    #     f.write("""
    # client_encryption_options:
    #   enabled: true
    #   certificate: /etc/scylla/ssl/server-cert.pem
    #   keyfile: /etc/scylla/ssl/server-key.pem
    #   truststore: /etc/scylla/ssl/ca-cert.pem
    #   require_client_auth: false
    # """)
    #
    # container = ScyllaContainer("scylladb/scylla:latest")
    # container.with_volume_mapping(
    #     ssl_certificates['cert_dir'],
    #     "/etc/scylla/ssl",
    #     mode="ro"
    # )
    # container.with_volume_mapping(
    #     str(ssl_config_path),
    #     "/etc/scylla/scylla.yaml",
    #     mode="ro"
    # )
    #
    # with container:
    #     # Wait for container to be ready
    #     container.get_connection_url()
    #     yield container


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
        Requires testcontainers package and Docker
    """
    pytest.skip("Testcontainers integration pending - see docs/plans/SSL_TLS_INTEGRATION_TEST_PLAN.md")
    
    # TODO: Implement Cassandra testcontainers integration
    # from testcontainers.cassandra import CassandraContainer
    # 
    # Implementation similar to scylla_ssl_container but with
    # Cassandra-specific SSL configuration


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
