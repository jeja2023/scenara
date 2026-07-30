#!/usr/bin/env bash
set -euo pipefail

backup_dir="${1:?usage: verify-backup.sh BACKUP_DIRECTORY}"
backup_dir="$(realpath "$backup_dir")"
test -f "$backup_dir/SHA256SUMS"
test -s "$backup_dir/postgres.dump"
test -d "$backup_dir/minio"
(
  cd "$backup_dir"
  sha256sum --check SHA256SUMS
)
