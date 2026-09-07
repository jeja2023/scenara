#!/bin/sh
set -eu

root_user="${SCENARA_INFRA_MINIO_ROOT_USER:?missing MinIO root user}"
root_password="${SCENARA_INFRA_MINIO_ROOT_PASSWORD:?missing MinIO root password}"

mc alias set local http://minio:9000 "$root_user" "$root_password" >/dev/null

for bucket in \
  scenara \
  scenara-datasets \
  scenara-data-manifests \
  scenara-data-imports \
  scenara-data-exports \
  scenara-artifacts \
  scenara-data-backups \
  scenara-model-artifacts
do
  mc mb --ignore-existing "local/$bucket" >/dev/null
  mc version enable "local/$bucket" >/dev/null 2>&1 || true
done

cat >/tmp/core-policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket"],"Resource":["arn:aws:s3:::scenara"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],"Resource":["arn:aws:s3:::scenara/*"]}]}
JSON
cat >/tmp/data-policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket"],"Resource":["arn:aws:s3:::scenara-datasets","arn:aws:s3:::scenara-data-manifests","arn:aws:s3:::scenara-data-imports","arn:aws:s3:::scenara-data-exports","arn:aws:s3:::scenara-artifacts","arn:aws:s3:::scenara-data-backups"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],"Resource":["arn:aws:s3:::scenara-datasets/*","arn:aws:s3:::scenara-data-manifests/*","arn:aws:s3:::scenara-data-imports/*","arn:aws:s3:::scenara-data-exports/*","arn:aws:s3:::scenara-artifacts/*","arn:aws:s3:::scenara-data-backups/*"]}]}
JSON
cat >/tmp/model-policy.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation","s3:ListBucket"],"Resource":["arn:aws:s3:::scenara-model-artifacts"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:AbortMultipartUpload","s3:ListMultipartUploadParts"],"Resource":["arn:aws:s3:::scenara-model-artifacts/*"]}]}
JSON

create_user() {
  user="$1"
  password="$2"
  policy="$3"

  if ! mc admin user info local "$user" >/dev/null 2>&1; then
    mc admin user add local "$user" "$password" >/dev/null
  fi
  if ! mc admin policy info local "$policy" >/dev/null 2>&1; then
    mc admin policy create local "$policy" "/tmp/$policy-policy.json" >/dev/null
  fi
  mc admin policy attach local "$policy" --user "$user" >/dev/null
}

create_user "${SCENARA_CORE_S3_ACCESS_KEY:?missing Core S3 access key}" "${SCENARA_CORE_S3_SECRET_KEY:?missing Core S3 secret key}" core
create_user "${SCENARA_DATA_S3_ACCESS_KEY:?missing Data S3 access key}" "${SCENARA_DATA_S3_SECRET_KEY:?missing Data S3 secret key}" data
create_user "${SCENARA_MODEL_S3_ACCESS_KEY:?missing Model S3 access key}" "${SCENARA_MODEL_S3_SECRET_KEY:?missing Model S3 secret key}" model

echo "shared MinIO buckets and least-privilege users are ready"
