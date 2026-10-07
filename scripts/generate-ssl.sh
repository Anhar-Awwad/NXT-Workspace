#!/bin/bash
set -e

CERT_DIR="$(dirname "$0")/../deployment/nginx/ssl"
mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$CERT_DIR/cert.key" \
  -out "$CERT_DIR/cert.crt" \
  -subj "/CN=nextcloud-internal"

chmod 600 "$CERT_DIR/cert.key"
chmod 644 "$CERT_DIR/cert.crt"

echo "SSL certificate created in $CERT_DIR"