BEGIN;

CREATE TABLE IF NOT EXISTS scenara_control_plane_records (
    record_type text NOT NULL CHECK (record_type ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    record_id text NOT NULL CHECK (record_id ~ '^[A-Za-z0-9_.:-]{2,160}$'),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (record_type, tenant_id, project_id, record_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_control_plane_scope_idx
    ON scenara_control_plane_records (tenant_id, project_id, record_type, updated_at DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0009_control_plane_records')
ON CONFLICT (version) DO NOTHING;

COMMIT;
