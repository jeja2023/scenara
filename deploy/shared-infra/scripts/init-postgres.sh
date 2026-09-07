#!/bin/sh
set -eu

admin_user="${SCENARA_INFRA_POSTGRES_ADMIN_USER:-scenara_admin}"
admin_password="${SCENARA_INFRA_POSTGRES_ADMIN_PASSWORD:?missing admin password}"

export PGPASSWORD="$admin_password"

create_database() {
  role="$1"
  password="$2"
  database="$3"

  psql -v ON_ERROR_STOP=1 -h postgres -U "$admin_user" -d postgres \
    -v role_name="$role" -v role_password="$password" -v database_name="$database" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'role_name')\gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'role_name', :'role_password')\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database_name', :'role_name')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name')\gexec
SQL

  psql -v ON_ERROR_STOP=1 -h postgres -U "$admin_user" -d "$database" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
}

create_database scenara "${SCENARA_CORE_DB_PASSWORD:?missing Core database password}" scenara
create_database scenara_data "${SCENARA_DATA_DB_PASSWORD:?missing Data database password}" scenara_data
create_database scenara_model "${SCENARA_MODEL_DB_PASSWORD:?missing Model database password}" scenara_model

echo "shared PostgreSQL databases are ready: scenara, scenara_data, scenara_model"
