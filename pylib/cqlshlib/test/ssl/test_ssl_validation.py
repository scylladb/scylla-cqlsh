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
SSL/TLS certificate validation and hostname verification tests.

Tests certificate validation scenarios:
- Valid certificates
- Expired certificates
- Self-signed certificates
- Hostname verification
- Certificate chain validation
"""

import pytest


@pytest.mark.skip(reason="Requires SSL-enabled container - see docs/plans/SSL_TLS_INTEGRATION_TEST_PLAN.md")
class TestCertificateValidation:
    """Certificate validation tests."""
    
    def test_valid_certificate_accepted(self, scylla_ssl_container, ssl_certificates):
        """Test that valid certificates are accepted."""
        # TODO: Implement
        pass
    
    def test_expired_certificate_rejected(self, scylla_ssl_container):
        """Test that expired certificates are rejected when validation is enabled."""
        # TODO: Create expired certificate and test
        pass
    
    def test_self_signed_with_validation(self, scylla_ssl_container, ssl_certificates):
        """Test self-signed certificate with validation enabled."""
        # TODO: Implement
        pass
    
    def test_certificate_chain_validation(self, scylla_ssl_container, ssl_certificates):
        """Test that certificate chain is properly validated."""
        # TODO: Implement
        pass


@pytest.mark.skip(reason="Requires SSL-enabled container")
class TestHostnameVerification:
    """Hostname verification tests."""
    
    def test_hostname_verification_enabled(self, scylla_ssl_container):
        """Test hostname verification when enabled."""
        # TODO: Implement
        pass
    
    def test_hostname_verification_disabled(self, scylla_ssl_container):
        """Test that connection works with hostname verification disabled."""
        # TODO: Implement
        pass
    
    def test_hostname_mismatch_rejected(self, scylla_ssl_container):
        """Test that hostname mismatch is rejected when verification is on."""
        # TODO: Create certificate with wrong hostname and test
        pass
