#!/bin/bash
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

# Generate SSL/TLS certificates for testing
# This script creates a complete certificate chain for testing:
# - CA certificate
# - Server certificate (signed by CA)
# - Client certificate (signed by CA, for mutual TLS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${CERT_DIR:-${SCRIPT_DIR}/certs}"

echo "Generating SSL/TLS certificates in: ${CERT_DIR}"
mkdir -p "${CERT_DIR}"
cd "${CERT_DIR}"

# Generate CA private key and certificate
echo "1. Generating CA certificate..."
openssl req -new -x509 -nodes -days 365 \
  -keyout ca-key.pem -out ca-cert.pem \
  -subj "/CN=Test CA/O=ScyllaDB Testing/C=US" \
  2>/dev/null

# Generate server private key and certificate signing request
echo "2. Generating server certificate..."
openssl req -new -nodes -days 365 \
  -keyout server-key.pem -out server-req.pem \
  -subj "/CN=localhost/O=ScyllaDB Testing/C=US" \
  2>/dev/null

# Sign server certificate with CA
openssl x509 -req -in server-req.pem \
  -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -days 365 \
  -out server-cert.pem \
  2>/dev/null

# Generate client private key and certificate signing request
echo "3. Generating client certificate (for mutual TLS)..."
openssl req -new -nodes -days 365 \
  -keyout client-key.pem -out client-req.pem \
  -subj "/CN=test-client/O=ScyllaDB Testing/C=US" \
  2>/dev/null

# Sign client certificate with CA
openssl x509 -req -in client-req.pem \
  -CA ca-cert.pem -CAkey ca-key.pem \
  -CAcreateserial -days 365 \
  -out client-cert.pem \
  2>/dev/null

# Clean up CSR files
rm -f server-req.pem client-req.pem ca-cert.srl

# Set appropriate permissions
chmod 644 *.pem
chmod 600 *-key.pem

echo "Certificate generation complete!"
echo ""
echo "Generated files:"
echo "  CA Certificate:      ca-cert.pem"
echo "  CA Private Key:      ca-key.pem (keep secure!)"
echo "  Server Certificate:  server-cert.pem"
echo "  Server Private Key:  server-key.pem (keep secure!)"
echo "  Client Certificate:  client-cert.pem"
echo "  Client Private Key:  client-key.pem (keep secure!)"
echo ""
echo "Note: These certificates are for TESTING ONLY and should never be used in production."
