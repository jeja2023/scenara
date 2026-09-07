#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?usage: restore.sh BACKUP_DIRECTORY --confirm}"
confirmation="${2:-}"
test "$confirmation" = "--confirm" || {
  echo "restore replaces the Scenara database and object bucket; pass --confirm" >&2
  exit 2
}
backup_dir="$(realpath "$backup_dir")"
test "$backup_dir" != "/"
compose_file="${SCENARA_COMPOSE_FILE:-$(dirname "$0")/../compose.yml}"
env_file="${SCENARA_COMPOSE_ENV_FILE:?set SCENARA_COMPOSE_ENV_FILE}"
infra_file="${SCENARA_INFRA_COMPOSE_FILE:-$(dirname "$0")/../shared-infra/compose.yml}"
infra_env_file="${SCENARA_INFRA_COMPOSE_ENV_FILE:?set SCENARA_INFRA_COMPOSE_ENV_FILE}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
infra=(docker compose --env-file "$infra_env_file" -f "$infra_file")

bash "$(dirname "$0")/verify-backup.sh" "$backup_dir"
data_only="${SCENARA_RESTORE_DATA_ONLY:-false}"
if test "$data_only" != "true"; then
  "${compose[@]}" stop api batch-worker stream-worker scheduler
fi
"${infra[@]}" exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d scenara --clean --if-exists --no-owner --no-privileges' < "$backup_dir/postgres.dump"
"${infra[@]}" run --rm --no-deps -T --entrypoint /bin/sh -v "$backup_dir/minio:/backup:ro" minio-init -c 'mc alias set local http://minio:9000 "$SCENARA_INFRA_MINIO_ROOT_USER" "$SCENARA_INFRA_MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite --remove /backup local/scenara'
if test "$data_only" != "true"; then
  "${compose[@]}" up -d --no-build api batch-worker stream-worker scheduler
fi
