#!/bin/bash
# =============================================================================
# Generate self-signed TLS certificates for local development
# =============================================================================
set -e

CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERT_DIR"

DAYS=365
SUBJECT="/C=US/ST=CA/L=SanFrancisco/O=FraudPlatform/CN=fraud.local"

echo "==> Generating CA key and certificate..."
openssl genrsa -out "$CERT_DIR/ca.key" 2048
openssl req -x509 -new -nodes -key "$CERT_DIR/ca.key" \
    -sha256 -days "$DAYS" \
    -out "$CERT_DIR/ca.crt" \
    -subj "$SUBJECT"

echo "==> Generating server key and CSR..."
openssl genrsa -out "$CERT_DIR/server.key" 2048
openssl req -new -key "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.csr" \
    -subj "/C=US/ST=CA/L=SanFrancisco/O=FraudPlatform/CN=*.fraud.local"

# SAN extension
cat > "$CERT_DIR/san.ext" << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = fraud.local
DNS.2 = *.fraud.local
DNS.3 = localhost
IP.1 = 127.0.0.1
EOF

echo "==> Signing server certificate with CA..."
openssl x509 -req -in "$CERT_DIR/server.csr" \
    -CA "$CERT_DIR/ca.crt" \
    -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial \
    -out "$CERT_DIR/server.crt" \
    -days "$DAYS" \
    -sha256 \
    -extfile "$CERT_DIR/san.ext"

rm -f "$CERT_DIR/server.csr" "$CERT_DIR/san.ext" "$CERT_DIR/ca.srl"

echo ""
echo "==> Certificates generated in $CERT_DIR:"
ls -la "$CERT_DIR/"
echo ""
echo "Files:"
echo "  ca.crt      — Certificate Authority certificate"
echo "  ca.key      — CA private key (keep secure)"
echo "  server.crt  — Server certificate"
echo "  server.key  — Server private key"
