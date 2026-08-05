BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS scenara_control_plane_session_token_idx
    ON scenara_control_plane_records ((document->>'token_sha256'))
    WHERE record_type = 'session';

CREATE INDEX IF NOT EXISTS scenara_control_plane_session_expiry_idx
    ON scenara_control_plane_records (((document->>'expires_at')::double precision))
    WHERE record_type = 'session';

INSERT INTO scenara_schema_migrations (version)
VALUES ('0011_session_token_index')
ON CONFLICT (version) DO NOTHING;

COMMIT;
