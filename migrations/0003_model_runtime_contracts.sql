BEGIN;

-- Import pre-contract model packages into a fail-closed legacy runtime namespace.
-- Operators can read and retire these records after upgrade, but must admit a new
-- formal package version with a configured runtime_model_id before runtime switching.
UPDATE scenara_model_packages
SET manifest = manifest || jsonb_build_object(
    'schema_version', '1.0',
    'runtime_model_id', COALESCE(NULLIF(manifest->>'runtime_model_id', ''), 'legacy/' || model_id),
    'source_uri', CASE
        WHEN (manifest->>'source_uri') LIKE ('%@sha256:' || sha256::text)
             OR (manifest->>'source_uri') LIKE ('%#sha256=' || sha256::text)
            THEN manifest->>'source_uri'
        ELSE (manifest->>'source_uri') || '@sha256:' || sha256::text
    END,
    'model_card', CASE
        WHEN (manifest->>'model_card') ~ '(@sha256:|#sha256=)[0-9a-f]{64}$'
            THEN manifest->>'model_card'
        ELSE (manifest->>'model_card') || '@sha256:' || sha256::text
    END,
    'evaluation_evidence', jsonb_build_array(CASE
        WHEN (manifest->>'model_card') ~ '(@sha256:|#sha256=)[0-9a-f]{64}$'
            THEN manifest->>'model_card'
        ELSE (manifest->>'model_card') || '@sha256:' || sha256::text
    END)
)
WHERE manifest->>'schema_version' IS DISTINCT FROM '1.0';

ALTER TABLE scenara_model_releases
    ADD COLUMN IF NOT EXISTS capability text;

UPDATE scenara_model_releases AS release
SET capability = COALESCE(
    NULLIF(release.document->>'capability', ''),
    NULLIF(package.manifest->>'capability', '')
)
FROM scenara_model_packages AS package
WHERE release.model_id = package.model_id
  AND release.version = package.version
  AND release.capability IS NULL;

UPDATE scenara_model_releases AS release
SET document = release.document || jsonb_build_object(
    'schema_version', '1.0',
    'capability', release.capability,
    'runtime_model_id', package.manifest->>'runtime_model_id'
)
FROM scenara_model_packages AS package
WHERE release.model_id = package.model_id
  AND release.version = package.version
  AND (
      release.document->>'capability' IS NULL
      OR release.document->>'runtime_model_id' IS NULL
  );

UPDATE scenara_model_deployment_events AS event
SET document = event.document || jsonb_build_object(
    'schema_version', '1.0',
    'capability', package.manifest->>'capability',
    'runtime_model_id', package.manifest->>'runtime_model_id',
    'package_sha256', package.sha256::text
)
FROM scenara_model_packages AS package
WHERE event.model_id = package.model_id
  AND event.version = package.version
  AND (
      event.document->>'capability' IS NULL
      OR event.document->>'runtime_model_id' IS NULL
      OR event.document->>'package_sha256' IS NULL
  );

ALTER TABLE scenara_model_releases
    ALTER COLUMN capability SET NOT NULL;

DROP INDEX IF EXISTS scenara_model_releases_one_active_idx;

CREATE UNIQUE INDEX IF NOT EXISTS scenara_model_releases_one_active_capability_idx
    ON scenara_model_releases (tenant_id, project_id, capability)
    WHERE status = 'active';

INSERT INTO scenara_schema_migrations (version)
VALUES ('0003_model_runtime_contracts')
ON CONFLICT (version) DO NOTHING;

COMMIT;
