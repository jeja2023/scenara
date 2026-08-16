# Scenara 景枢私有化部署

升级、恢复式回滚、运行探针、指标和告警基线见 [OPERATIONS.md](OPERATIONS.md)。

The supported 1.0 target is Ubuntu x86_64 with Docker Engine, Docker Compose v2, and exactly one measurable NVIDIA GPU. PostgreSQL/pgvector, Redis, and MinIO are part of the production Compose topology. The data-service images are pinned by manifest digest. Python production dependencies are installed only from `requirements/production.lock` with SHA-256 verification.

## Configure

Create a deployment environment file from .env.production.example. Replace every example credential. Generate the secret encryption key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; the checked-in placeholder is intentionally invalid. Keep the file outside source control.

The qualified model package directory must include the private OCR adapter module named by `SCENARA_OCR_ENGINE_FACTORY` (for example `approved_ocr_adapter:create_engine`). Its factory must return a production-ready engine with `model_id`, `version`, `production_ready=true`, `predict`, and the declared layout capabilities. Compose mounts this directory read-only at `/opt/scenara/models` for every process that builds the runtime. The repository does not provide a production OCR adapter.

Validate without starting services:

    docker compose --env-file deploy/.env.production -f deploy/compose.yml config --quiet

Start an online installation:

    docker compose --env-file deploy/.env.production -f deploy/compose.yml up -d --build

After the API health check passes, open the bundled Chinese console at `http://<host>:8000/console/`. The same versioned image serves the API and console, so an offline deployment cannot accidentally combine different contract versions.

Private RTSP/RTMP/HTTP source addresses are rejected by default. Set `SCENARA_ALLOW_PRIVATE_MEDIA_SOURCES=true` only when the deployment network isolates workers from management and metadata endpoints; URL credentials remain encrypted in the configured Secret Store.

The API, batch worker, stream worker, and scheduler share one versioned image. Batch and real-time runs use separate Redis stream consumer groups.

## Offline bundle

On a connected Ubuntu build host:

    SCENARA_COMPOSE_ENV_FILE=deploy/.env.production \
      SCENARA_MODEL_BUNDLE_DIR=/secure/qualified-model-packages \
      deploy/scripts/build-offline-bundle.sh /srv/scenara-release

Transfer the generated tar archive through the project's controlled channel, extract it, then install on the target:

    deploy/scripts/install-offline.sh \
      /srv/scenara-offline-0.3.0-dev.22 \
      /secure/scenara.env \
      /secure/offline-installer-result.json

The qualified model package directory is mandatory and is copied into the checksummed offline bundle; the repository never supplies or substitutes model weights. The installer verifies Ubuntu 24.04 x86_64, Docker Engine 27+, Docker Compose 2.29+, CUDA 12.8 driver compatibility, and exactly one measurable NVIDIA GPU before loading images. GPU memory is recorded but has no fixed lower or upper qualification limit. It starts Compose with `--no-build --wait`, verifies the dependency readiness endpoint and Chinese console, and rejects any required service that is not running. The optional third argument is written atomically as a schema-version 1.0 JSON result and is never allowed to overwrite an existing file.

The builder also writes `scenara-offline-<tag>.release-identity.json` beside the archive. It records the source commit, application image digest, archive SHA-256, OpenAPI SHA-256, and aggregate qualified-model-set SHA-256 required by the strict release manifest. Keep this companion file with the release artifacts.

Model weights are not bundled by this repository. Install only packages that pass MODEL_ASSETS.md and the strict release evidence gate.

## Backup and restore

Create and verify a PostgreSQL plus MinIO backup:

    SCENARA_COMPOSE_ENV_FILE=/secure/scenara.env \
      deploy/scripts/backup.sh /srv/backups/scenara-2026-07-29

Restore is destructive and requires explicit confirmation:

    SCENARA_COMPOSE_ENV_FILE=/secure/scenara.env \
      deploy/scripts/restore.sh /srv/backups/scenara-2026-07-29 --confirm

Redis is intentionally excluded because it is a delivery, lease, and short-term event service rather than a system of record. PostgreSQL and MinIO are restored before workers restart.

CI may set `SCENARA_RESTORE_DATA_ONLY=true` to exercise PostgreSQL and MinIO restoration without starting GPU workers. This mode is not valid 1.0 release evidence; the target-host drill must use the default full restart path.

Backups record container image names, Compose version, the SHA-256 of the deployment file, and source commit provenance. Resolved Compose configuration is deliberately excluded because it contains deployment secrets.

A successful script run is not release evidence by itself. Record the target, execution timestamp, checksums, recovery objectives, and observed loss window in the strict evidence manifest.
