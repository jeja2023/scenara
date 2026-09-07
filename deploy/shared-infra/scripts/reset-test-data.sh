#!/usr/bin/env bash
set -euo pipefail

test "${SCENARA_ENVIRONMENT_NAME:-}" = "test" || {
  echo "refusing reset: set SCENARA_ENVIRONMENT_NAME=test" >&2
  exit 2
}
test "${1:-}" = "--confirm-test-only" || {
  echo "reset deletes all Core, Data and Model test data; pass --confirm-test-only" >&2
  exit 2
}

script_dir="$(dirname "$0")"
compose_file="${SCENARA_INFRA_COMPOSE_FILE:-$script_dir/../compose.yml}"
env_file="${SCENARA_INFRA_COMPOSE_ENV_FILE:?set SCENARA_INFRA_COMPOSE_ENV_FILE}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")

for database in scenara scenara_data scenara_model; do
  "${compose[@]}" exec -T postgres sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database' AND pid <> pg_backend_pid();\" -c \"DROP DATABASE IF EXISTS $database;\" -c \"CREATE DATABASE $database OWNER $database;\""
done

"${compose[@]}" run --rm --no-deps --entrypoint /bin/sh minio-init -c '
  mc alias set local http://minio:9000 "$SCENARA_INFRA_MINIO_ROOT_USER" "$SCENARA_INFRA_MINIO_ROOT_PASSWORD" >/dev/null
  for bucket in scenara scenara-datasets scenara-data-manifests scenara-data-imports scenara-data-exports scenara-artifacts scenara-data-backups scenara-model-artifacts; do
    mc rm --recursive --force --dangerous "local/$bucket" >/dev/null 2>&1 || true
  done
'

"${compose[@]}" run --rm postgres-init >/dev/null
"${compose[@]}" run --rm minio-init >/dev/null
echo "test data reset completed; run each application's migration separately"
