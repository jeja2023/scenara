#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?usage: restore.sh BACKUP_DIRECTORY --confirm}"
confirmation="${2:-}"
test "$confirmation" = "--confirm" || {
  echo "restore replaces all three databases and shared object buckets; pass --confirm" >&2
  exit 2
}
backup_dir="$(realpath "$backup_dir")"
test "$backup_dir" != "/"
test -f "$backup_dir/SHA256SUMS"
(
  cd "$backup_dir"
  sha256sum --check SHA256SUMS
)

script_dir="$(dirname "$0")"
compose_file="${SCENARA_INFRA_COMPOSE_FILE:-$script_dir/../compose.yml}"
env_file="${SCENARA_INFRA_COMPOSE_ENV_FILE:?set SCENARA_INFRA_COMPOSE_ENV_FILE}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")

for database in scenara scenara_data scenara_model; do
  "${compose[@]}" exec -T postgres sh -c "pg_restore -U \"\$POSTGRES_USER\" -d '$database' --clean --if-exists --no-owner --no-privileges" < "$backup_dir/postgres/$database.dump"
done

"${compose[@]}" run --rm --no-deps -T --entrypoint /bin/sh -v "$backup_dir/objects:/backup:ro" minio-init -c '
  mc alias set local http://minio:9000 "$SCENARA_INFRA_MINIO_ROOT_USER" "$SCENARA_INFRA_MINIO_ROOT_PASSWORD" >/dev/null
  for bucket in scenara scenara-datasets scenara-data-manifests scenara-data-imports scenara-data-exports scenara-artifacts scenara-data-backups scenara-model-artifacts; do
    mc mirror --overwrite --remove "/backup/$bucket" "local/$bucket"
  done
'

echo "shared infrastructure restore completed; restart Core, Data and Model separately"
