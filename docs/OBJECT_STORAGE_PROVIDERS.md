# Certified S3 object providers

Scenara depends on the S3 contract, not on a specific storage product. PostgreSQL
is the source of truth for records and object references. Certified S3 providers
store original media, previews, run artifacts, and immutable structured results.

## Provider status

| Provider | Status | Intended deployment |
|---|---|---|
| MinIO | Certified baseline | Single-site private and offline deployments |
| Amazon S3 | Candidate | AWS-managed production |
| Alibaba Cloud OSS S3 API | Candidate | Mainland China managed production |
| Ceph RGW | Candidate | Existing private-cloud storage platforms |

Candidate means that the adapter is configurable for the provider, not that the
release has qualification evidence for it. A provider becomes certified only
after its target version passes `tests/object_store_contract.py` against the real
service and the resulting report is attached to release evidence.

The contract covers immutable idempotent upload and concurrent conflict rejection,
checksum-protected multipart upload, full and file-based download verification,
metadata, existence, deletion, reconnect recovery, presigned PUT/GET, and tagged
lifecycle rules.

Run the S3 qualification tests with provider-specific environment variables:

```powershell
$env:SCENARA_RUN_INTEGRATION = "1"
$env:SCENARA_INTEGRATION_S3_ENDPOINT = "https://objects.example.com"
$env:SCENARA_INTEGRATION_S3_ACCESS_KEY = "..."
$env:SCENARA_INTEGRATION_S3_SECRET_KEY = "..."
python -m pytest -q tests/integration/test_services.py -k "s3_provider or presigned_media"
```

Use an isolated qualification bucket. The suite creates unique keys and removes
them, while the lifecycle test updates bucket lifecycle configuration.

## Integrity and immutability

All published writes are immutable by default. `If-None-Match: *` prevents a
different payload from replacing an existing key; retrying the same key and
SHA-256 is idempotent. Multipart completion uses the same condition. The only
mutable object class is encrypted internal secret storage, which opts into an
explicit atomic overwrite path.

Every write stores SHA-256 as S3 metadata and sends the native S3 checksum when
supported. Media execution, result loading, artifact reads, and Redis queue
recovery compare object bytes or metadata with the PostgreSQL reference.

## Credentials, TLS, and encryption

Static credentials remain supported for MinIO and offline installations. Leave
the access key, secret key, and session token empty to use the AWS/default
credential provider chain, including instance roles and workload identity. STS
session credentials can be supplied with `SCENARA_S3_SESSION_TOKEN`.

TLS verification is enabled by default. `SCENARA_S3_CA_BUNDLE` installs a private
CA trust path. `SCENARA_S3_SERVER_SIDE_ENCRYPTION` supports `AES256` and `aws:kms`;
the latter may use `SCENARA_S3_KMS_KEY_ID`.

`SCENARA_S3_ADDRESSING_STYLE` accepts `auto`, `path`, or `virtual`. MinIO commonly
uses `path`; OSS normally requires `virtual`.

## Lifecycle ownership

PostgreSQL retention records and the Scenara scheduler remain authoritative.
When `SCENARA_S3_LIFECYCLE_ENABLED=true`, the provider installs tag-based rules
for raw media, previews, and structured results one day after the application
retention deadline. This grace period lets the scheduler mark database records
first. Incomplete direct uploads expire after one day.

Enable lifecycle management only for an identity allowed to call
`PutBucketLifecycleConfiguration`. Otherwise provision equivalent rules outside
Scenara and keep the setting false.

## Direct transfer

Set `SCENARA_S3_PRESIGNED_URLS_ENABLED=true` to expose the controlled direct
transfer workflow:

1. `POST /api/v1/media/uploads/presign` binds a PUT URL to tenant, project,
   filename, content type, exact byte length, SHA-256, and expiry.
2. The client uploads bytes directly to the provider using every returned header.
3. `POST /api/v1/media/uploads/complete` verifies the HMAC token, size, and digest
   before creating the asset and deleting the pending object.
4. `GET /api/v1/media/assets/{asset_id}/download-url` returns a short-lived GET URL
   only after authorization and integrity verification.

In container deployments, set `SCENARA_S3_PUBLIC_ENDPOINT_URL` to an endpoint
reachable by external clients. The internal endpoint remains available for API
and worker traffic. Python SDK `upload_asset_direct` and TypeScript SDK
`uploadAssetDirect` implement this workflow.
