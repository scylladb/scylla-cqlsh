# SSL/TLS Integration Test Implementation Plan

## Overview
This document outlines the implementation plan for adding client encryption (SSL/TLS) integration tests to the scylla-cqlsh repository.

## Current State Analysis

### Existing Infrastructure
- **Test Framework**: pytest-based tests in `pylib/cqlshlib/test/`
- **SSL Support**: cqlsh already supports SSL via `--ssl` flag and config file
- **SSL Handling Module**: `pylib/cqlshlib/sslhandling.py` manages SSL context creation
- **GitHub Actions**: Two integration test jobs (Scylla and Cassandra) using Docker
- **Dependencies**: scylla-driver

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

## Implementation Approach

### Testcontainers-Based Approach

#### Description
Use python-testcontainers with the built-in ScyllaContainer class for automated, pytest-integrated SSL/TLS testing.

#### Advantages
- Built-in ScyllaDB support via `ScyllaContainer` class
- Automatic container lifecycle management (start/cleanup)
- Native pytest fixture integration
- Cleaner, more maintainable code than manual Docker
- Isolated test environments with guaranteed cleanup
- Port conflict resolution handled automatically
- Consistent with modern Python testing practices

#### Implementation Steps

1. **Add testcontainers Dependency**
   - Add `testcontainers` to `pylib/requirements.txt`
   - Package provides `ScyllaContainer` with ScyllaDB defaults

2. **Create SSL Configuration Files**
   - Location: `pylib/cqlshlib/test/docker/`
   - Files:
     - `scylla-ssl.yaml`: Scylla configuration with SSL enabled
     - `generate_certs.sh`: Script to generate certificates (already exists)

3. **Create Testcontainers Fixture**
   - Location: `pylib/cqlshlib/test/conftest.py` (extend existing)
   - Add pytest fixture: `scylla_ssl_container`
   - Example implementation:
     ```python
     from testcontainers.scylla import ScyllaContainer
     from .ssl_utils import generate_ssl_certificates
     
     @pytest.fixture(scope='module')
     def scylla_ssl_container():
         # Generate SSL certificates
         certs = generate_ssl_certificates()
         
         # Create ScyllaDB container with SSL configuration
         container = ScyllaContainer("scylladb/scylla:latest")
         container.with_volume_mapping(certs['cert_dir'], "/etc/scylla/ssl", mode="ro")
         container.with_volume_mapping("./scylla-ssl.yaml", "/etc/scylla/scylla.yaml", mode="ro")
         
         with container:
             # Wait for ScyllaDB to be ready
             container.get_connection_url()  # Validates connectivity
             yield container
     ```

4. **Create SSL Integration Tests**
   - Location: `pylib/cqlshlib/test/test_ssl_integration.py` (extend existing)
   - Test cases using the fixture:
     - `test_ssl_basic_connection(scylla_ssl_container)`
     - `test_ssl_with_validation(scylla_ssl_container)`
     - `test_ssl_client_auth(scylla_ssl_container)`
     - `test_ssl_cqlshrc_config(scylla_ssl_container)`
     - `test_ssl_copy_command(scylla_ssl_container)`

#### Advantages Over Manual Docker
- No need for docker-compose files
- Automatic port mapping and conflict resolution
- Better integration with pytest lifecycle
- Cleaner test code with context managers
- Container cleanup guaranteed even on test failures
- Simplified CI/CD integration

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

Add jobs to `.github/workflows/build-push.yml` using testcontainers:

1. **integration_test_scylla_ssl**
   - Use testcontainers for ScyllaDB with SSL
   - Run SSL-specific tests
   - Automatic container lifecycle management

2. **integration_test_cassandra_ssl**
   - Use testcontainers for Cassandra with SSL
   - Run SSL-specific tests
   - Ensure compatibility

### Example Workflow Addition

```yaml
integration_test_scylla_ssl:
  name: Integration Tests (Scylla SSL/TLS with Testcontainers)
  if: "!contains(github.event.pull_request.labels.*.name, 'disable-integration-test')"
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.x'

    - name: Install Dependencies
      run: |
        pip install -r ./pylib/requirements.txt
        ./reloc/build_reloc.sh

    - name: Run SSL Integration Tests
      run: |
        # Testcontainers handles container lifecycle automatically
        pytest ./pylib/cqlshlib/test/test_ssl_integration.py -v -m ssl
      env:
        # Testcontainers will use Docker automatically
        DOCKER_HOST: unix:///var/run/docker.sock
```

**Note**: Testcontainers eliminates the need for manual Docker commands, certificate mounting, and container cleanup. All of this is handled by the pytest fixtures.

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

### Implementation (3 weeks)
Focus on testcontainers-based approach with comprehensive test coverage:

1. **Week 1**: Setup
   - Add testcontainers to dependencies
   - Create certificate generation utilities
   - Create Scylla SSL configuration file
   - Set up testcontainers pytest fixtures

2. **Week 2**: Core Tests
   - Implement basic SSL connection tests with testcontainers
   - Test certificate validation
   - Test configuration methods (cqlshrc, env vars, CLI flags)

3. **Week 3**: CI Integration
   - Add GitHub Actions workflows using testcontainers
   - Test on Scylla and Cassandra
   - Documentation and polish

## Dependencies

### Python Packages
- `testcontainers`: For ScyllaDB/Cassandra container management (add to pylib/requirements.txt)
- `cryptography`: Optional, for advanced certificate generation
- Existing: `scylla-driver`, `pytest`

### External Dependencies
- OpenSSL (for certificate generation via bash script)
- Docker (automatically used by testcontainers)

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
- Testcontainers automatically handles Docker dependencies and container lifecycle. Tests will be skipped if Docker is not available.
- The `@pytest.mark.ssl` marker is already configured for SSL tests.
- Testcontainers provides better isolation and cleanup compared to manual Docker management.

## References

- Scylla SSL/TLS documentation: https://docs.scylladb.com/stable/operating-scylla/security/client-node-encryption.html
- Cassandra SSL documentation: https://cassandra.apache.org/doc/latest/cassandra/operating/security.html
- cqlsh SSL handling: `pylib/cqlshlib/sslhandling.py`
- python-testcontainers documentation: https://testcontainers-python.readthedocs.io/en/latest/
- ScyllaContainer documentation: https://testcontainers-python.readthedocs.io/en/latest/modules/scylla/README.html
