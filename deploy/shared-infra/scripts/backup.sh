#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?usage: backup.sh BACKUP_DIRECTORY}"
backup_dir="$(realpath -m "$backup_dir")"
test "$backup_dir" != "/"
mkdir -p "$backup_dir/postgres" "$backup_dir/objects"

script_dir="$(dirname "$0")"
compose_file="${SCENARA_INFRA_COMPOSE_FILE:-$script_dir/../compose.yml}"
env_file="${SCENARA_INFRA_COMPOSE_ENV_FILE:?set SCENARA_INFRA_COMPOSE_ENV_FILE}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")

for database in scenara scenara_data scenara_model; do
  "${compose[@]}" exec -T postgres sh -c "pg_dump -U \"\$POSTGRES_USER\" -d '$database' --format=custom" > "$backup_dir/postgres/$database.dump"
done

"${compose[@]}" run --rm --no-deps -T --entrypoint /bin/sh -v "$backup_dir/objects:/backup" minio-init -c '
  mc alias set local http://minio:9000 "$SCENARA_INFRA_MINIO_ROOT_USER" "$SCENARA_INFRA_MINIO_ROOT_PASSWORD" >/dev/null
  for bucket in scenara scenara-datasets scenara-data-manifests scenara-data-imports scenara-data-exports scenara-artifacts scenara-data-backups scenara-model-artifacts; do
    mkdir -p "/backup/$bucket"
    mc mirror --overwrite "local/$bucket" "/backup/$bucket"
  done
'

"${compose[@]}" config --images | sort -u > "$backup_dir/container-images.txt"
sha256sum "$compose_file" > "$backup_dir/compose-file.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$backup_dir/created-at.txt"
(
  cd "$backup_dir"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

echo "shared infrastructure backup created at $backup_dir"
