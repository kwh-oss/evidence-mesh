#!/usr/bin/env bash
set -euo pipefail

host="api.linsixuan.cn"
secret_root="/home/ubuntu/evidence-mesh/deploy/secrets"
trust="${secret_root}/leader/trust-bundle.pem"
cert="${secret_root}/leader/client-cert.pem"
key="${secret_root}/leader/client-key.pem"

sudo docker ps \
  --filter name=evidence-mtls-stage \
  --format '{{.Names}} {{.Status}} {{.Ports}}'

for port in 8440 8441 8442 8443; do
  curl --noproxy '*' --silent --show-error --fail \
    --resolve "${host}:${port}:127.0.0.1" \
    --cacert "${trust}" \
    --cert "${cert}" \
    --key "${key}" \
    "https://${host}:${port}/health" >/dev/null
  echo "POSITIVE_MTLS_OK_${port}"

  if curl --noproxy '*' --silent --show-error --fail \
    --resolve "${host}:${port}:127.0.0.1" \
    --cacert "${trust}" \
    "https://${host}:${port}/health" >/dev/null 2>&1; then
    echo "NEGATIVE_UNEXPECTED_SUCCESS_${port}"
    exit 1
  fi
  echo "NO_CERT_REJECTED_${port}"
done
