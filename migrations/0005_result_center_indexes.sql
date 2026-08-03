BEGIN;

-- Result center reads are tenant/project scoped and newest-first.
CREATE INDEX IF NOT EXISTS scenara_run_results_domain_created_idx
    ON scenara_run_results (tenant_id, project_id, domain, created_at DESC);

CREATE INDEX IF NOT EXISTS scenara_run_results_media_kind_idx
    ON scenara_run_results (tenant_id, project_id, (summary->>'media_kind'), created_at DESC);

CREATE INDEX IF NOT EXISTS scenara_run_results_resource_name_idx
    ON scenara_run_results (tenant_id, project_id, (lower(summary->>'resource_name')));

INSERT INTO scenara_schema_migrations (version)
VALUES ('0005_result_center_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
