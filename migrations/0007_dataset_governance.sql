BEGIN;

CREATE TABLE IF NOT EXISTS scenara_datasets (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    dataset_id text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'active', 'archived')),
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, dataset_id)
);

CREATE INDEX IF NOT EXISTS scenara_datasets_updated_idx
    ON scenara_datasets (tenant_id, project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS scenara_dataset_versions (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    version_id text NOT NULL,
    dataset_id text NOT NULL,
    version text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'validated', 'published', 'retired')),
    manifest_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, version_id),
    UNIQUE (tenant_id, project_id, dataset_id, version),
    FOREIGN KEY (tenant_id, project_id, dataset_id)
        REFERENCES scenara_datasets (tenant_id, project_id, dataset_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_dataset_versions_lookup_idx
    ON scenara_dataset_versions (tenant_id, project_id, dataset_id, created_at DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0007_dataset_governance')
ON CONFLICT (version) DO NOTHING;

COMMIT;
