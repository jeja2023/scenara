#!/usr/bin/env bash
set -euo pipefail

output_dir="${1:?usage: generate-internal-ca.sh OUTPUT_DIRECTORY}"
output_dir="$(realpath -m "$output_dir")"
test "$output_dir" != "/"
test ! -e "$output_dir" || {
  echo "refusing to overwrite existing certificate directory: $output_dir" >&2
  exit 2
}

command -v openssl >/dev/null || {
  echo "openssl is required" >&2
  exit 2
}

umask 077
mkdir -p "$output_dir"/{ca,postgres,redis,minio,core,data,model}

openssl genrsa -out "$output_dir/ca/ca.key" 4096 >/dev/null 2>&1
openssl req -x509 -new -nodes -sha256 -days 3650 \
  -key "$output_dir/ca/ca.key" \
  -out "$output_dir/ca/ca.crt" \
  -subj "/C=CN/O=Scenara/OU=Platform/CN=Scenara Internal Root CA" >/dev/null 2>&1

issue_leaf() {
  name="$1"
  filename="$2"
  san_list="$3"
  directory="$output_dir/$name"
  config="$directory/openssl.cnf"
  cat > "$config" <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = req_ext
prompt = no
[req_distinguished_name]
CN = $filename.scenara.internal
[req_ext]
subjectAltName = $san_list
extendedKeyUsage = serverAuth
EOF
  openssl genrsa -out "$directory/server.key" 3072 >/dev/null 2>&1
  openssl req -new -key "$directory/server.key" -out "$directory/server.csr" -config "$config" >/dev/null 2>&1
  openssl x509 -req -sha256 -days 825 \
    -in "$directory/server.csr" \
    -CA "$output_dir/ca/ca.crt" -CAkey "$output_dir/ca/ca.key" \
    -CAcreateserial -out "$directory/server.crt" \
    -extfile "$config" -extensions req_ext >/dev/null 2>&1
  rm -f "$directory/server.csr" "$directory/openssl.cnf"
  chmod 0640 "$directory/server.key"
  chmod 0644 "$directory/server.crt"
}

issue_leaf postgres postgres "DNS:postgres.scenara.internal,DNS:postgres"
issue_leaf redis redis "DNS:redis.scenara.internal,DNS:redis"
issue_leaf minio minio "DNS:minio.scenara.internal,DNS:minio"
issue_leaf core core "DNS:core.scenara.internal,DNS:api,DNS:localhost,IP:127.0.0.1"
issue_leaf data data "DNS:data.scenara.internal,DNS:data-api,DNS:localhost,IP:127.0.0.1"
issue_leaf model model "DNS:model.scenara.internal,DNS:model-api,DNS:localhost,IP:127.0.0.1"

cp "$output_dir/minio/server.crt" "$output_dir/minio/public.crt"
cp "$output_dir/minio/server.key" "$output_dir/minio/private.key"
cp "$output_dir/ca/ca.crt" "$output_dir/ca.crt"
chmod 0644 "$output_dir/ca.crt"
rm -f "$output_dir"/{postgres,redis,minio,core,data,model}/server.csr

if [ "$(id -u)" -eq 0 ]; then
  chown 999:999 "$output_dir/postgres/server.key" "$output_dir/redis/server.key"
  chown 10001:10001 "$output_dir/core/server.key"
  chown 1000:1000 "$output_dir/data/server.key" "$output_dir/model/server.key"
  chown 0:0 "$output_dir/minio/private.key"
else
  echo "warning: run this script as root if the service private keys must remain mode 0640" >&2
fi

echo "created Scenara internal CA and service certificates in $output_dir"
