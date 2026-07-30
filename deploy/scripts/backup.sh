#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?usage: backup.sh BACKUP_DIRECTORY}"
backup_dir="$(realpath -m "$backup_dir")"
test "$backup_dir" != "/"
mkdir -p "$backup_dir/minio"
compose_file="${SCENARA_COMPOSE_FILE:-$(dirname "$0")/../compose.yml}"
env_file="${SCENARA_COMPOSE_ENV_FILE:?set SCENARA_COMPOSE_ENV_FILE}"
compose=(docker compose --env-file "$env_file" -f "$compose_file")

"${compose[@]}" exec -T postgres pg_dump -U scenara -d scenara --format=custom > "$backup_dir/postgres.dump"
"${compose[@]}" run --rm --no-deps -T   --entrypoint /bin/sh   -v "$backup_dir/minio:/backup"   minio-init -c 'mc alias set local http://minio:9000 "$ACCESS_KEY" "$SECRET_KEY" >/dev/null && mc mirror --overwrite local/scenara /backup'
"${compose[@]}" config --images | sort -u > "$backup_dir/container-images.txt"
docker compose version > "$backup_dir/compose-version.txt"
sha256sum "$compose_file" > "$backup_dir/compose-file.sha256"
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
