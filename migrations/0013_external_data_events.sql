BEGIN;

CREATE TABLE IF NOT EXISTS scenara_external_events (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    event_id text NOT NULL,
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    received_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, project_id, event_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_external_events_received_idx
    ON scenara_external_events (received_at DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0013_external_data_events')
ON CONFLICT (version) DO NOTHING;

COMMIT;
