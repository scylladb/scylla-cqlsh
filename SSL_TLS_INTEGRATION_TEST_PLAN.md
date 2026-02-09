# SSL/TLS Integration Test Implementation Plan

## Overview
This document outlines the implementation plan for adding client encryption (SSL/TLS) integration tests to the scylla-cqlsh repository.

## Current State Analysis

### Existing Infrastructure
- **Test Framework**: pytest-based tests in `pylib/cqlshlib/test/`
- **SSL Support**: cqlsh already supports SSL via `--ssl` flag and config file
- **SSL Handling Module**: `pylib/cqlshlib/sslhandling.py` manages SSL context creation
- **GitHub Actions**: Two integration test jobs (Scylla and Cassandra) using Docker
- **Dependencies**: scylla-driver, scylla-ccm support in requirements

### SSL Configuration in cqlsh
cqlsh supports SSL through:
1. Command-line flag: `--ssl`
2. Config file (`~/.cqlshrc`) with `[ssl]` section:
   - `validate`: Enable/disable certificate validation
   - `check_hostname`: Enable/disable hostname checking
   - `certfile`: Path to CA certificate
   - `userkey`: Path to client private key
   - `usercert`: Path to client certificate
3. Environment variables:
   - `SSL_VALIDATE`
   - `SSL_CHECK_HOSTNAME`
   - `SSL_CERTFILE`
   - `SSL_VERSION`

## Implementation Options

### Option 1: scylla-ccm Based Approach

#### Description
Use scylla-ccm (Cassandra Cluster Manager) to create local clusters with SSL/TLS enabled.

#### Advantages
- More control over cluster configuration
- Can test both Scylla and Cassandra
- Easier to configure SSL certificates and encryption settings
- Better for local development and debugging
- CCM is already a dependency in `pylib/requirements.txt`

#### Implementation Steps

1. **Create SSL Certificate Generation Utility**
   - Location: `pylib/cqlshlib/test/ssl_utils.py`
   - Functions:
     - `generate_self_signed_cert()`: Generate CA, server, and client certificates
     - `create_ssl_config_dir()`: Create temporary directory with certificates
     - `cleanup_ssl_config()`: Remove temporary SSL files

2. **Create CCM Cluster Fixture**
   - Location: `pylib/cqlshlib/test/conftest.py` (extend existing)
   - Add pytest fixture: `ccm_cluster_with_ssl`
   - Responsibilities:
     - Generate SSL certificates
     - Create CCM cluster with SSL configuration
     - Start cluster
     - Wait for cluster readiness
     - Yield cluster connection info
     - Teardown cluster and cleanup certificates

3. **Create SSL Integration Tests**
   - Location: `pylib/cqlshlib/test/test_ssl_integration.py`
   - Test cases:
     - `test_ssl_connection_with_validation()`: Connect with certificate validation
     - `test_ssl_connection_without_validation()`: Connect with validation disabled
     - `test_ssl_with_client_auth()`: Mutual TLS (client certificates)
     - `test_ssl_hostname_verification()`: Test hostname checking
     - `test_ssl_via_config_file()`: SSL configured via cqlshrc
     - `test_ssl_via_environment_vars()`: SSL configured via env vars
     - `test_ssl_copy_command()`: Test COPY command over SSL

4. **CCM Configuration Details**
   ```python
   # Example CCM SSL configuration
   ccm_config = {
       'client_encryption_options': {
           'enabled': True,
           'certificate': '/path/to/server.crt',
           'keyfile': '/path/to/server.key',
           'truststore': '/path/to/ca.pem',
           'require_client_auth': False  # or True for mutual TLS
       }
   }
   ```

#### Challenges
- Requires Java runtime for CCM
- More complex setup and teardown
- May be slower than Docker approach
- Certificate generation complexity

---

### Option 2: Docker-Based Approach

#### Description
Use Docker containers with pre-configured SSL/TLS settings, similar to existing integration tests.

#### Advantages
- Faster startup/teardown
- Consistent with existing CI infrastructure
- Easier to integrate with GitHub Actions
- Can use pre-built Docker images with SSL
- Isolated environment

#### Implementation Steps

1. **Create SSL-Enabled Docker Configuration**
   - Location: `pylib/cqlshlib/test/docker/`
   - Files:
     - `docker-compose-ssl.yml`: Docker Compose configuration
     - `scylla-ssl.yaml`: Scylla configuration with SSL
     - `cassandra-ssl.yaml`: Cassandra configuration with SSL
     - `generate_certs.sh`: Script to generate certificates

2. **Docker Compose Configuration Example**
   ```yaml
   version: '3.8'
   services:
     scylla-ssl:
       image: scylladb/scylla:latest
       volumes:
         - ./ssl-certs:/etc/scylla/ssl:ro
         - ./scylla-ssl.yaml:/etc/scylla/scylla.yaml:ro
       command: --cluster-name test-ssl
       healthcheck:
         test: ["CMD", "cqlsh", "-e", "SELECT * FROM system.local"]
         interval: 10s
         timeout: 5s
         retries: 30
   ```

3. **Create SSL Test Helper Module**
   - Location: `pylib/cqlshlib/test/docker_ssl_helper.py`
   - Functions:
     - `setup_docker_ssl_cluster()`: Start Docker container with SSL
     - `get_ssl_connection_params()`: Return connection parameters
     - `teardown_docker_ssl_cluster()`: Stop and remove container

4. **Create SSL Integration Tests**
   - Location: `pylib/cqlshlib/test/test_ssl_docker.py`
   - Test cases (similar to CCM approach):
     - `test_docker_ssl_basic_connection()`
     - `test_docker_ssl_with_validation()`
     - `test_docker_ssl_client_auth()`
     - `test_docker_ssl_cqlshrc_config()`

#### Challenges
- Need to build custom Docker images or configure at runtime
- Less control over server configuration
- Certificate management within containers
- Potential port conflicts in CI

---

## Recommended Hybrid Approach

Combine both approaches for comprehensive testing:

### Phase 1: Docker-Based Tests (Quick Win)
Start with Docker-based tests for immediate value:
- Faster to implement
- Integrates easily with existing CI
- Good for basic SSL functionality testing

### Phase 2: CCM-Based Tests (Comprehensive)
Add CCM-based tests for advanced scenarios:
- More control over configuration
- Better for edge cases and complex scenarios
- Useful for local development

## SSL/TLS Encryption Setup Details

### Certificate Generation

#### Using OpenSSL
```bash
# Generate CA certificate
openssl req -new -x509 -nodes -days 365 \
  -keyout ca-key.pem -out ca-cert.pem \
  -subj "/CN=Test CA"

# Generate server certificate
openssl req -new -nodes -days 365 \
  -keyout server-key.pem -out server-req.pem \
  -subj "/CN=localhost"

openssl x509 -req -in server-req.pem \
  -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -days 365 \
  -out server-cert.pem

# Generate client certificate (for mutual TLS)
openssl req -new -nodes -days 365 \
  -keyout client-key.pem -out client-req.pem \
  -subj "/CN=test-client"

openssl x509 -req -in client-req.pem \
  -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -days 365 \
  -out client-cert.pem
```

#### Python Certificate Generation
```python
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import datetime

def generate_certificates():
    # Generate CA
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")]))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    # Similar for server and client certs...
```

### Scylla SSL Configuration

```yaml
# scylla.yaml
client_encryption_options:
  enabled: true
  certificate: /etc/scylla/ssl/server-cert.pem
  keyfile: /etc/scylla/ssl/server-key.pem
  truststore: /etc/scylla/ssl/ca-cert.pem
  require_client_auth: false
```

### Cassandra SSL Configuration

```yaml
# cassandra.yaml
client_encryption_options:
  enabled: true
  optional: false
  keystore: /etc/cassandra/ssl/server.keystore
  keystore_password: changeit
  require_client_auth: false
  truststore: /etc/cassandra/ssl/server.truststore
  truststore_password: changeit
```

### cqlshrc Configuration

```ini
[connection]
hostname = localhost
port = 9042
ssl = true

[ssl]
validate = true
check_hostname = true
certfile = /path/to/ca-cert.pem
userkey = /path/to/client-key.pem
usercert = /path/to/client-cert.pem
```

## GitHub Actions Integration

### New Workflow Jobs

Add three new jobs to `.github/workflows/build-push.yml`:

1. **integration_test_scylla_ssl**
   - Start Scylla with SSL enabled
   - Run SSL-specific tests
   - Use Docker approach for speed

2. **integration_test_cassandra_ssl**
   - Start Cassandra with SSL enabled
   - Run SSL-specific tests
   - Ensure compatibility

3. **integration_test_enterprise_ssl** (Optional)
   - Test with Scylla Enterprise if available
   - May require different certificate configuration

### Example Workflow Addition

```yaml
integration_test_scylla_ssl:
  name: Integration Tests (Scylla SSL/TLS)
  if: "!contains(github.event.pull_request.labels.*.name, 'disable-integration-test')"
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Generate SSL Certificates
      run: |
        mkdir -p ssl-certs
        cd ssl-certs
        # Certificate generation script
        ../pylib/cqlshlib/test/docker/generate_certs.sh

    - name: Start Scylla with SSL
      run: |
        docker run -d \
          -v $(pwd)/ssl-certs:/etc/scylla/ssl:ro \
          -v $(pwd)/pylib/cqlshlib/test/docker/scylla-ssl.yaml:/etc/scylla/scylla.yaml:ro \
          --name scylla-ssl \
          scylladb/scylla:latest --cluster-name test-ssl
        
        # Wait for SSL port
        export CQL_TEST_HOST=$(docker inspect --format='{{ .NetworkSettings.IPAddress }}' scylla-ssl)
        while ! openssl s_client -connect ${CQL_TEST_HOST}:9042 </dev/null 2>/dev/null; do
          sleep 1
        done
        echo "CQL_TEST_HOST=${CQL_TEST_HOST}" >> $GITHUB_ENV

    - name: Run SSL Tests
      run: |
        pip install -r ./pylib/requirements.txt
        ./reloc/build_reloc.sh
        pytest ./pylib/cqlshlib/test/test_ssl*.py -v
      env:
        SSL_CERTFILE: ssl-certs/ca-cert.pem
```

## Testing Strategy

### Test Coverage Areas

1. **Basic SSL Connection**
   - Connect with `--ssl` flag
   - Connect without validation
   - Connect with validation enabled

2. **Certificate Validation**
   - Valid certificate
   - Expired certificate (should fail)
   - Self-signed certificate with validation
   - Hostname verification

3. **Client Authentication (Mutual TLS)**
   - Client certificate required
   - Client certificate optional
   - Missing client certificate (should fail when required)

4. **Configuration Methods**
   - Command-line flags
   - Config file (.cqlshrc)
   - Environment variables
   - Precedence testing (env > config > default)

5. **Operations over SSL**
   - Basic queries (SELECT, INSERT, UPDATE, DELETE)
   - COPY FROM/TO commands
   - DDL operations
   - Authentication with SSL

6. **Error Handling**
   - Invalid certificates
   - Certificate/hostname mismatch
   - SSL handshake failures
   - Clear error messages

## Implementation Timeline

### Minimal Implementation (Suggested)
Focus on Docker-based approach with basic test coverage:

1. **Week 1**: Setup
   - Create certificate generation utilities
   - Create Docker SSL configuration
   - Set up test fixtures

2. **Week 2**: Core Tests
   - Implement basic SSL connection tests
   - Test certificate validation
   - Test configuration methods

3. **Week 3**: CI Integration
   - Add GitHub Actions workflows
   - Test on Scylla and Cassandra
   - Documentation

### Full Implementation
Add CCM-based tests and comprehensive coverage:

4. **Week 4**: CCM Integration
   - CCM cluster fixtures
   - Advanced test scenarios
   - Client authentication tests

5. **Week 5**: Polish
   - Edge case testing
   - Error handling verification
   - Performance considerations

## Dependencies

### Python Packages
- `cryptography`: For certificate generation (add to pylib/requirements.txt)
- `pytest-docker`: Optional, for better Docker integration
- `pyOpenSSL`: Alternative for SSL utilities

### External Dependencies
- OpenSSL (for certificate generation)
- Docker (for Docker-based tests)
- Java 8+ (for CCM-based tests)
- scylla-ccm (already in requirements)

## Security Considerations

1. **Test Certificates**
   - Use clearly marked test certificates
   - Short expiration periods
   - Not for production use

2. **Certificate Storage**
   - Store in test directories only
   - Clean up after tests
   - Don't commit private keys to repository

3. **Secrets Management**
   - No hardcoded passwords
   - Use environment variables for sensitive data
   - GitHub Actions secrets for CI

## Success Criteria

- [ ] SSL connection tests pass with Scylla
- [ ] SSL connection tests pass with Cassandra
- [ ] Certificate validation works correctly
- [ ] Client authentication (mutual TLS) works
- [ ] Configuration via cqlshrc works
- [ ] Configuration via environment variables works
- [ ] GitHub Actions workflows run successfully
- [ ] Documentation is complete
- [ ] No security vulnerabilities introduced

## Notes

- The existing `sni_proxy` test suite works with SSL/TLS but is configured by python-driver, not by cqlsh directly. This implementation will test cqlsh's SSL handling specifically.
- Tests should be skipped gracefully if required dependencies (Docker, OpenSSL, etc.) are not available.
- Consider adding a marker `@pytest.mark.ssl` to easily run/skip SSL tests.

## References

- Scylla SSL/TLS documentation: https://docs.scylladb.com/stable/operating-scylla/security/client-node-encryption.html
- Cassandra SSL documentation: https://cassandra.apache.org/doc/latest/cassandra/operating/security.html
- cqlsh SSL handling: `pylib/cqlshlib/sslhandling.py`
