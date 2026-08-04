BEGIN;

CREATE TABLE IF NOT EXISTS scenara_indexes (
    index_id text PRIMARY KEY,
    schema_version text NOT NULL,
    domain text NOT NULL,
    record_kind text NOT NULL CHECK (record_kind IN ('vector', 'text', 'multimodal')),
    vector_dimension integer,
    vector_model_id text,
    vector_model_version text,
    distance_metric text,
    threshold double precision,
    text_analyzer text,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS scenara_index_records (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    record_id text NOT NULL,
    index_id text NOT NULL REFERENCES scenara_indexes (index_id),
    domain text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('vector', 'text', 'multimodal')),
    source_type text NOT NULL,
    source_id text NOT NULL,
    asset_id text,
    run_id text,
    unit_id text,
    object_id text,
    artifact_id text,
    page_number integer,
    pts_ms bigint,
    feature_id text,
    text text,
    vector jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('ready', 'pending', 'failed', 'deleted')),
    created_at timestamptz NOT NULL,
    expires_at timestamptz,
    deleted_at timestamptz,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, record_id)
);

CREATE INDEX IF NOT EXISTS scenara_index_records_lookup_idx
    ON scenara_index_records (tenant_id, project_id, index_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS scenara_index_records_source_idx
    ON scenara_index_records (tenant_id, project_id, source_type, source_id, status);
CREATE INDEX IF NOT EXISTS scenara_index_records_text_idx
    ON scenara_index_records USING gin (to_tsvector('simple', coalesce(text, '')));

INSERT INTO scenara_schema_migrations (version)
VALUES ('0006_index_contract')
ON CONFLICT (version) DO NOTHING;

COMMIT;
