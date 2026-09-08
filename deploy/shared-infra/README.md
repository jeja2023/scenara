# Scenara shared infrastructure

This stack owns only shared dependencies. Core, Data and Model remain independent Compose projects and connect to the external `platform` network created here.

The single PostgreSQL container contains three isolated databases and roles:

- `scenara` / `scenara`
- `scenara_data` / `scenara_data`
- `scenara_model` / `scenara_model`

The single MinIO container contains separate buckets and least-privilege users. Core uses `scenara`, Data uses the `scenara-*` data buckets, and Model uses `scenara-model-artifacts`. Redis is shared with logical database `0` for Core and `1` for Data; Model does not currently require Redis.

Copy `.env.example` outside the repository, replace every placeholder, and start this stack first:

```bash
docker compose --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml config --quiet
docker compose --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml up -d --wait
docker compose --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml run --rm postgres-init
docker compose --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml run --rm minio-init
```

The application Compose files must use the same `SCENARA_PLATFORM_NETWORK` and connect to `postgres`, `redis`, and `minio` on that network. The published host ports bind only to loopback and are for maintenance; applications should use the container DNS names.

## Separate application deployment

Deploy each application from its own repository. Do not start the old Core/Data infrastructure Compose files at the same time:

```bash
# 1. Shared infrastructure, from scenara
docker compose -p scenara-infra-test \
  --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml up -d --wait
docker compose -p scenara-infra-test \
  --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml run --rm postgres-init
docker compose -p scenara-infra-test \
  --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml run --rm minio-init

# 2. Data, from scenara-data
docker compose -p scenara-data-test \
  --env-file /secure/scenara-data-test.env \
  -f deploy/compose.shared-test.yml up -d --build --wait

# 3. Core, from scenara
docker compose -p scenara-core-test \
  --env-file /secure/scenara-core-test.env \
  -f deploy/compose.yml run --rm preflight
docker compose -p scenara-core-test \
  --env-file /secure/scenara-core-test.env \
  -f deploy/compose.yml up -d --build --wait

# 4. Model, from scenara-model
docker compose -p scenara-model-test \
  --env-file /secure/scenara-model-test.env \
  -f deploy/compose.shared-test.yml up -d --build --wait
```

The Data-first order is intentional: Core's Data client can then pass signed requests immediately, while Data's Outbox may safely retry its callback to Core until Core is ready. For an initial test, verify `http://127.0.0.1:58081/readyz`, `http://127.0.0.1:8000/readyz`, and `http://127.0.0.1:58080/health`.

This bundle is intended for the current test-data environment. Production should move PostgreSQL, Redis and S3-compatible storage to managed services or add TLS, backups, monitoring and secret-file integration before using a production profile.

For the single-host internal production deployment, generate a private CA and service certificates on the Ubuntu host:

```bash
sudo deploy/shared-infra/scripts/generate-internal-ca.sh /secure/scenara-certs
```

The certificate names include `postgres.scenara.internal`, `redis.scenara.internal`, `minio.scenara.internal`, `core.scenara.internal`, `data.scenara.internal` and `model.scenara.internal`. Start the infrastructure with the TLS overlay:

```bash
docker compose --env-file /secure/scenara-infra.env \
  -f deploy/shared-infra/compose.yml \
  -f deploy/shared-infra/compose.tls.yml up -d --wait postgres redis minio
```

The TLS overlay removes the host maintenance ports. Application Compose files must mount the same certificate directory through `SCENARA_PLATFORM_CERTS_DIR` and use the internal HTTPS names.

Back up and restore all three databases and all shared buckets from this stack. Stop the three application Compose projects before restoring:

```bash
SCENARA_INFRA_COMPOSE_ENV_FILE=/secure/scenara-infra.env \
  deploy/shared-infra/scripts/backup.sh /srv/backups/scenara-shared-2026-09-07

SCENARA_INFRA_COMPOSE_ENV_FILE=/secure/scenara-infra.env \
  deploy/shared-infra/scripts/restore.sh /srv/backups/scenara-shared-2026-09-07 --confirm
```

Redis is deliberately not included in the backup because it only stores queues, leases and short-lived coordination state. After a restore, start Data before Core so its Outbox can resume safely.

For the current test-only environment, reset all three databases and shared buckets with two explicit safeguards:

```bash
SCENARA_ENVIRONMENT_NAME=test \
SCENARA_INFRA_COMPOSE_ENV_FILE=/secure/scenara-infra.env \
  deploy/shared-infra/scripts/reset-test-data.sh --confirm-test-only
```

Do not use this command for staging or production data.
