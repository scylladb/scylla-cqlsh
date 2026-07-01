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
SSL/TLS integration test module.

This package contains SSL/TLS integration tests for cqlsh, organized as:

Test Files:
-----------
- test_ssl_utilities.py: Tests for SSL certificate generation and utilities
- test_ssl_connection.py: Basic SSL connection tests
- test_ssl_validation.py: Certificate validation and hostname verification tests
- test_ssl_client_auth.py: Mutual TLS (client certificate) tests
- test_ssl_configuration.py: Configuration methods (cqlshrc, env vars, CLI) tests
- test_ssl_operations.py: SSL with various CQL operations (COPY, DDL, etc.)

Fixtures:
---------
All shared fixtures are defined in conftest.py including:
- ssl_certificates: Generate test certificates
- scylla_ssl_container: ScyllaDB container with SSL (via testcontainers)
- cassandra_ssl_container: Cassandra container with SSL (via testcontainers)

Usage:
------
Run all SSL tests:
    pytest pylib/cqlshlib/test/ssl/ -v

Run specific test file:
    pytest pylib/cqlshlib/test/ssl/test_ssl_connection.py -v

Run with SSL marker:
    pytest -m ssl -v
"""

# Mark all tests in this module as SSL tests
import pytest

pytestmark = pytest.mark.ssl
