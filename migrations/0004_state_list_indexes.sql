BEGIN;

CREATE INDEX IF NOT EXISTS scenara_media_assets_created_idx
    ON scenara_media_assets (tenant_id, project_id, created_at DESC, asset_id DESC);

CREATE INDEX IF NOT EXISTS scenara_media_sources_created_idx
    ON scenara_media_sources (tenant_id, project_id, created_at DESC, source_id DESC);

CREATE INDEX IF NOT EXISTS scenara_runs_asset_active_idx
    ON scenara_runs (tenant_id, project_id, ((document ->> 'asset_id')))
    WHERE status NOT IN ('completed', 'failed', 'cancelled');

CREATE INDEX IF NOT EXISTS scenara_runs_source_active_idx
    ON scenara_runs (tenant_id, project_id, ((document ->> 'source_id')))
    WHERE status NOT IN ('completed', 'failed', 'cancelled');

INSERT INTO scenara_schema_migrations (version)
VALUES ('0004_state_list_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
