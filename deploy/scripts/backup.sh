#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?usage: backup.sh BACKUP_DIRECTORY}"
backup_dir="$(realpath -m "$backup_dir")"
test "$backup_dir" != "/"
mkdir -p "$backup_dir/minio"
compose_file="${SCENARA_COMPOSE_FILE:-$(dirname "$0")/../compose.yml}"
env_file="${SCENARA_COMPOSE_ENV_FILE:?set SCENARA_COMPOSE_ENV_FILE}"
infra_file="${SCENARA_INFRA_COMPOSE_FILE:-$(dirname "$0")/../shared-infra/compose.yml}"
infra_env_file="${SCENARA_INFRA_COMPOSE_ENV_FILE:?set SCENARA_INFRA_COMPOSE_ENV_FILE}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
infra=(docker compose --env-file "$infra_env_file" -f "$infra_file")

"${infra[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d scenara --format=custom' > "$backup_dir/postgres.dump"
"${infra[@]}" run --rm --no-deps -T --entrypoint /bin/sh -v "$backup_dir/minio:/backup" minio-init -c 'mc alias set local http://minio:9000 "$SCENARA_INFRA_MINIO_ROOT_USER" "$SCENARA_INFRA_MINIO_ROOT_PASSWORD" >/dev/null && mc mirror --overwrite local/scenara /backup'
{ "${compose[@]}" config --images; "${infra[@]}" config --images; } | sort -u > "$backup_dir/container-images.txt"
docker compose version > "$backup_dir/compose-version.txt"
sha256sum "$compose_file" > "$backup_dir/compose-file.sha256"
sha256sum "$infra_file" > "$backup_dir/infra-compose-file.sha256"
source_root="$(realpath "$(dirname "$0")/../..")"
if git -C "$source_root" rev-parse HEAD >/dev/null 2>&1; then
  git -C "$source_root" rev-parse HEAD > "$backup_dir/source-commit.txt"
elif test -s "$source_root/source-commit.txt"; then
  cp "$source_root/source-commit.txt" "$backup_dir/source-commit.txt"
else
  echo "source commit provenance is unavailable" >&2
  exit 2
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$backup_dir/created-at.txt"
(
  cd "$backup_dir"
  find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)
bash "$(dirname "$0")/verify-backup.sh" "$backup_dir"
