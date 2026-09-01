# Scenara 景枢私有化部署

升级、恢复式回滚、运行探针、指标和告警基线见 [OPERATIONS.md](OPERATIONS.md)；上线逐项验收见 [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)。

The supported 1.0 target is Ubuntu x86_64 with Docker Engine, Docker Compose v2, and one or more measurable NVIDIA GPUs. PostgreSQL/pgvector, Redis, and MinIO are part of the production Compose topology. The data-service images are pinned by manifest digest. Python production dependencies are installed only from `requirements/production.lock` with SHA-256 verification.

## Configure

Generate a deployment candidate outside the repository, then fill external endpoints, image digest, allowed hosts and approved model factories:

    python scripts/generate_production_env.py --output /secure/scenara.env
    python scripts/validate_production_config.py --env-file /secure/scenara.env

The validator does not print secret values. On Linux it rejects group/world-readable env files, reused trust-boundary secrets, short credentials, invalid Fernet keys, wildcard Host/proxy trust, unqualified built-in adapters, mutable image references and non-TLS Data URLs unless isolated internal HTTP is explicitly allowed.

The default `deploy/compose.yml` is the personal deployment profile. It uses the local policy provider and does not require, read, or mount an enterprise license. The signed enterprise policy implementation remains available as an optional extension. To enable it, set `SCENARA_ENTERPRISE_LICENSE_FILE` and `SCENARA_ENTERPRISE_PUBLIC_KEY_FILE` to readable files and add `-f deploy/compose.enterprise.yml` to each Compose command.

Both GPU workers request all visible GPUs by default. A qualified production host should normally pin different `GPU_DEVICE_IDS` per worker through a Compose override; sharing all GPUs is only a starting topology and requires measured concurrency evidence. The legacy inference adapter discovers visible devices from `CUDA_VISIBLE_DEVICES`, NVIDIA device nodes, or `nvidia-smi`.

The qualified model package directory must include private OCR, Behavior and Fashion adapter modules named by `SCENARA_OCR_ENGINE_FACTORY`, `SCENARA_BEHAVIOR_ENGINE_FACTORY` and `SCENARA_FASHION_ENGINE_FACTORY`. Each factory must return a qualified engine with immutable model identity, `production_ready=true`, the required inference methods and declared capabilities. Compose mounts this directory read-only at `/opt/scenara/models`. Built-in reference adapters are intentionally rejected by production validation.

Validate without starting services. The Compose `preflight` one-shot service repeats runtime validation before API startup:

    docker compose --env-file /secure/scenara.env -f deploy/compose.yml config --quiet

Build and push the release image in CI, record its digest in `SCENARA_IMAGE_REFERENCE`, then start behind a TLS reverse proxy. Do not use `--build` with a digest-pinned production reference. The default host binding is `127.0.0.1:8000`; direct non-loopback HTTP requires an explicit unsafe override:

    docker compose --env-file /secure/scenara.env -f deploy/compose.yml pull
    docker compose --env-file /secure/scenara.env -f deploy/compose.yml run --rm preflight
    docker compose --env-file /secure/scenara.env -f deploy/compose.yml run --rm migrate
    docker compose --env-file /secure/scenara.env -f deploy/compose.yml up -d --no-build --wait

For the optional enterprise profile, validate and start with both files:

    docker compose --env-file /secure/scenara.env \
      -f deploy/compose.yml -f deploy/compose.enterprise.yml config --quiet

    docker compose --env-file /secure/scenara.env \
      -f deploy/compose.yml -f deploy/compose.enterprise.yml run --rm preflight

    docker compose --env-file /secure/scenara.env \
      -f deploy/compose.yml -f deploy/compose.enterprise.yml up -d --no-build --wait

After the API health check passes, open the bundled Chinese console through the configured TLS domain, for example `https://scenara.example.com/console/`. Port 8000 remains loopback-only. The same versioned image serves the API and console, so an offline deployment cannot accidentally combine different contract versions.

Private RTSP/RTMP/HTTP source addresses are rejected by default. Set `SCENARA_ALLOW_PRIVATE_MEDIA_SOURCES=true` only when the deployment network isolates workers from management and metadata endpoints; URL credentials remain encrypted in the configured Secret Store.

The API, batch worker, stream worker, and scheduler share one versioned image. Batch and real-time runs use separate Redis stream consumer groups.

## Offline bundle

On a connected Ubuntu build host:

    SCENARA_COMPOSE_ENV_FILE=deploy/.env.production \

Private RTSP/RTMP/HTTP source addresses are rejected by default. Set `SCENARA_ALLOW_PRIVATE_MEDIA_SOURCES=true` only when the deployment network isolates workers from management and metadata endpoints; URL credentials remain encrypted in the configured Secret Store.

The API, batch worker, stream worker, and scheduler share one versioned image. Batch and real-time runs use separate Redis stream consumer groups.

## Offline bundle

On a connected Ubuntu build host:

    SCENARA_COMPOSE_ENV_FILE=deploy/.env.production \
      SCENARA_MODEL_BUNDLE_DIR=/secure/qualified-model-packages \
      deploy/scripts/build-offline-bundle.sh /srv/scenara-release

Transfer the generated tar archive through the project's controlled channel, extract it, then install on the target:

    deploy/scripts/install-offline.sh \
      /srv/scenara-offline-0.3.0-dev.40 \
      /secure/scenara.env \
      /secure/offline-installer-result.json

The qualified model package directory is mandatory and is copied into the checksummed offline bundle; the repository never supplies or substitutes model weights. The installer verifies Ubuntu 24.04 x86_64, Docker Engine 27+, Docker Compose 2.29+, CUDA 12.8 driver compatibility, and at least one measurable NVIDIA GPU before loading images. All visible GPUs are exposed to both GPU workers by default; the installer records GPU count and aggregate memory but imposes no fixed GPU-count or memory limit. It starts Compose with `--no-build --wait`, verifies the dependency readiness endpoint and Chinese console, and rejects any required service that is not running. The optional third argument is written atomically as a schema-version 1.0 JSON result and is never allowed to overwrite an existing file.

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
