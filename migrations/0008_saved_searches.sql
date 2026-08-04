BEGIN;

CREATE TABLE IF NOT EXISTS scenara_saved_searches (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    saved_search_id TEXT NOT NULL,
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('text', 'portrait')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY (tenant_id, project_id, saved_search_id),
    UNIQUE (tenant_id, project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_scenara_saved_searches_updated
    ON scenara_saved_searches (tenant_id, project_id, updated_at DESC, saved_search_id DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0008_saved_searches')
ON CONFLICT (version) DO NOTHING;

COMMIT;
