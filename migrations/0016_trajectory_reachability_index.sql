BEGIN;

-- 可达性探针按 last_seen_at 倒序取紧邻的前驱观测，既有索引只覆盖 first_seen_at。
CREATE INDEX IF NOT EXISTS scenara_trajectory_segment_identity_last_seen_idx
    ON scenara_trajectory_segments (tenant_id, project_id, identity_id, last_seen_at DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0016_trajectory_reachability_index')
ON CONFLICT (version) DO NOTHING;

COMMIT;
