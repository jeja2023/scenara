#!/usr/bin/env sh
set -eu

: "${PGHOST:=postgres}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=scenara}"
: "${PGUSER:=scenara}"

psql -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS scenara_schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

for migration in /migrations/*.sql; do
  test -f "$migration" || continue
  version="$(basename "$migration" .sql)"
  case "$version" in
    ""|*[!A-Za-z0-9._-]*)
      echo "unsupported migration filename: $migration" >&2
      exit 2
      ;;
  esac
  applied="$(psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM scenara_schema_migrations WHERE version = '$version'")"
  if test "$applied" = "1"; then
    printf 'migration %s already applied\n' "$version"
    continue
  fi
  printf 'applying migration %s\n' "$version"
  psql -v ON_ERROR_STOP=1 -f "$migration"
  applied="$(psql -v ON_ERROR_STOP=1 -tAc "SELECT 1 FROM scenara_schema_migrations WHERE version = '$version'")"
  test "$applied" = "1" || {
    echo "migration did not atomically record its version: $version" >&2
    exit 2
  }
done
