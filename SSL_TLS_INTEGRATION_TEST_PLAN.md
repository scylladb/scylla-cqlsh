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

### Docker-Based Approach

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
   - Test cases:
     - `test_docker_ssl_basic_connection()`
     - `test_docker_ssl_with_validation()`
     - `test_docker_ssl_client_auth()`
     - `test_docker_ssl_cqlshrc_config()`

#### Challenges
- Need to build custom Docker images or configure at runtime
- Less control over server configuration
- Certificate management within containers
- Potential port conflicts in CI

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

### Implementation (3 weeks)
Focus on Docker-based approach with comprehensive test coverage:

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

## Dependencies

### Python Packages
- `cryptography`: For certificate generation (add to pylib/requirements.txt)
- `pytest-docker`: Optional, for better Docker integration
- `pyOpenSSL`: Alternative for SSL utilities

### External Dependencies
- OpenSSL (for certificate generation)
- Docker (for Docker-based tests)

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
