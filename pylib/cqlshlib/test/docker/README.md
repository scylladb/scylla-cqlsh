# SSL/TLS Docker Test Utilities

This directory contains utilities for running SSL/TLS integration tests using Docker containers.

## Contents

- `generate_certs.sh`: Script to generate test SSL certificates
- `.gitignore`: Excludes generated certificates from version control

## Usage

### Generate Test Certificates

```bash
cd pylib/cqlshlib/test/docker
./generate_certs.sh
```

This creates a `certs/` directory with:
- CA certificate and key
- Server certificate and key
- Client certificate and key (for mutual TLS)

### Important Notes

- **These certificates are for TESTING ONLY**
- Never use these certificates in production
- Certificates are excluded from git via `.gitignore`
- Certificates expire after 365 days

## Future Extensions

This directory will contain:
- Docker Compose configurations for SSL-enabled clusters
- Scylla/Cassandra configuration files for SSL
- Helper scripts for managing SSL test containers
