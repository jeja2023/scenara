BEGIN;

ALTER TABLE scenara_surveillance_alerts
    ADD COLUMN IF NOT EXISTS occurrence_count integer NOT NULL DEFAULT 1
    CHECK (occurrence_count >= 1);

ALTER TABLE scenara_surveillance_debounce
    ADD COLUMN IF NOT EXISTS max_score double precision NOT NULL DEFAULT 0
    CHECK (max_score BETWEEN -1 AND 1);

ALTER TABLE scenara_surveillance_debounce
    ADD COLUMN IF NOT EXISTS occurrence_count integer NOT NULL DEFAULT 1
    CHECK (occurrence_count >= 1);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0015_surveillance_debounce_aggregates')
ON CONFLICT (version) DO NOTHING;

COMMIT;
