BEGIN;

-- PostgreSQL baseline for the independent scenara-data service.  Core never
-- creates or queries these tables; the standalone service owns this schema.
CREATE TABLE IF NOT EXISTS data_datasets (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    dataset_id text NOT NULL,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('draft', 'active', 'archived')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, project_id, dataset_id)
);

CREATE TABLE IF NOT EXISTS data_dataset_versions (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    version_id text NOT NULL,
    dataset_id text NOT NULL,
    version text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'building', 'ready', 'published', 'archived')),
    manifest_uri text NOT NULL,
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    lineage_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    authorization_id text NOT NULL,
    authorized_consumer_repository_ids jsonb NOT NULL DEFAULT '["scenara-model"]'::jsonb,
    sample_count integer NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz,
    PRIMARY KEY (tenant_id, project_id, version_id),
    UNIQUE (tenant_id, project_id, dataset_id, version),
    FOREIGN KEY (tenant_id, project_id, dataset_id)
        REFERENCES data_datasets (tenant_id, project_id, dataset_id)
);

CREATE TABLE IF NOT EXISTS data_samples (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    sample_id text NOT NULL,
    source_ref jsonb NOT NULL,
    content_sha256 text,
    media_type text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, project_id, sample_id)
);

CREATE TABLE IF NOT EXISTS data_outbox_events (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    occurred_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, project_id, event_id)
);

CREATE INDEX IF NOT EXISTS data_outbox_pending_idx
    ON data_outbox_events (status, occurred_at);

COMMIT;
