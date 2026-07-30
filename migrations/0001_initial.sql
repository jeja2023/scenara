BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS scenara_schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scenara_media_assets (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    asset_id text NOT NULL,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, asset_id)
);

CREATE TABLE IF NOT EXISTS scenara_media_sources (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    source_id text NOT NULL,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, source_id)
);

CREATE TABLE IF NOT EXISTS scenara_pipeline_versions (
    pipeline_id text NOT NULL,
    version text NOT NULL,
    domain text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'validated', 'approved', 'active', 'retired')),
    definition jsonb NOT NULL,
    definition_sha256 char(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz,
    PRIMARY KEY (pipeline_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS scenara_one_active_pipeline_version
    ON scenara_pipeline_versions (pipeline_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS scenara_model_packages (
    model_id text NOT NULL,
    version text NOT NULL,
    capability text NOT NULL,
    adapter text NOT NULL,
    sha256 char(64) NOT NULL,
    license_id text NOT NULL,
    source_uri text NOT NULL,
    vram_mb integer NOT NULL CHECK (vram_mb >= 0),
    production_ready boolean NOT NULL DEFAULT false,
    manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model_id, version)
);

CREATE TABLE IF NOT EXISTS scenara_runs (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    run_id text NOT NULL,
    domain text NOT NULL CHECK (domain ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    status text NOT NULL CHECK (
        status IN ('queued', 'running', 'pausing', 'paused', 'completed', 'failed', 'cancelling', 'cancelled')
    ),
    revision integer NOT NULL CHECK (revision > 0),
    priority integer NOT NULL DEFAULT 0 CHECK (priority BETWEEN -100 AND 100),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id)
);

CREATE INDEX IF NOT EXISTS scenara_runs_status_created_idx
    ON scenara_runs (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS scenara_runs_domain_created_idx
    ON scenara_runs (tenant_id, project_id, domain, created_at DESC);

CREATE TABLE IF NOT EXISTS scenara_idempotency_keys (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    request_hash char(64) NOT NULL,
    run_id text NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES scenara_runs (tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_run_events (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    run_id text NOT NULL,
    event_id bigint NOT NULL CHECK (event_id > 0),
    event_type text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id, event_id),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES scenara_runs (tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_run_results (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    run_id text NOT NULL,
    domain text NOT NULL,
    schema_version text NOT NULL,
    object_key text NOT NULL,
    sha256 char(64) NOT NULL,
    unit_count integer NOT NULL CHECK (unit_count >= 0),
    created_at timestamptz NOT NULL,
    summary jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, run_id),
    FOREIGN KEY (tenant_id, project_id, run_id)
        REFERENCES scenara_runs (tenant_id, project_id, run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_object_retention (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    object_key text NOT NULL,
    category text NOT NULL CHECK (category IN ('raw_media', 'preview', 'structured_result', 'biometric')),
    owner_type text NOT NULL CHECK (owner_type IN ('media_asset', 'run_result', 'portrait_enrollment')),
    owner_id text NOT NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz,
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id, project_id, object_key)
);

CREATE INDEX IF NOT EXISTS scenara_object_retention_expiry_idx
    ON scenara_object_retention (expires_at, object_key) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS scenara_object_retention_owner_idx
    ON scenara_object_retention (tenant_id, project_id, owner_type, owner_id);

CREATE TABLE IF NOT EXISTS scenara_webhook_subscriptions (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    endpoint_id text NOT NULL,
    url text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    event_types text[] NOT NULL,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, endpoint_id)
);

CREATE TABLE IF NOT EXISTS scenara_webhook_deliveries (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    delivery_id text NOT NULL,
    endpoint_id text NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'delivering', 'delivered', 'dead_letter')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, delivery_id),
    UNIQUE (tenant_id, project_id, endpoint_id, event_id),
    FOREIGN KEY (tenant_id, project_id, endpoint_id)
        REFERENCES scenara_webhook_subscriptions (tenant_id, project_id, endpoint_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_webhook_deliveries_due_idx
    ON scenara_webhook_deliveries (next_attempt_at, created_at)
    WHERE status IN ('pending', 'delivering');

CREATE TABLE IF NOT EXISTS scenara_feature_spaces (
    feature_space_id text PRIMARY KEY,
    domain text NOT NULL,
    modality text NOT NULL,
    model_id text NOT NULL,
    model_version text NOT NULL,
    dimension integer NOT NULL CHECK (dimension > 0),
    distance_metric text NOT NULL CHECK (distance_metric IN ('cosine', 'l2', 'inner_product')),
    threshold double precision,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (domain, modality, model_id, model_version, dimension, distance_metric)
);

CREATE TABLE IF NOT EXISTS scenara_features (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    feature_id text NOT NULL,
    feature_space_id text NOT NULL REFERENCES scenara_feature_spaces (feature_space_id),
    subject_type text NOT NULL,
    subject_id text NOT NULL,
    embedding vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    PRIMARY KEY (tenant_id, project_id, feature_id)
);

CREATE INDEX IF NOT EXISTS scenara_features_subject_idx
    ON scenara_features (tenant_id, project_id, feature_space_id, subject_type, subject_id);

CREATE TABLE IF NOT EXISTS scenara_portrait_identities (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    identity_id text NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, identity_id)
);

CREATE TABLE IF NOT EXISTS scenara_portrait_enrollments (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    enrollment_id text NOT NULL,
    identity_id text NOT NULL,
    feature_id text NOT NULL,
    feature_space_id text NOT NULL,
    modality text NOT NULL CHECK (modality IN ('face', 'body', 'gait', 'appearance')),
    quality double precision NOT NULL CHECK (quality BETWEEN 0 AND 1),
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, enrollment_id),
    UNIQUE (tenant_id, project_id, feature_id),
    FOREIGN KEY (tenant_id, project_id, identity_id)
        REFERENCES scenara_portrait_identities (tenant_id, project_id, identity_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, feature_id)
        REFERENCES scenara_features (tenant_id, project_id, feature_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_portrait_enrollments_identity_idx
    ON scenara_portrait_enrollments (tenant_id, project_id, identity_id, created_at DESC);

CREATE TABLE IF NOT EXISTS scenara_enterprise_usage (
    tenant_id text NOT NULL,
    metric text NOT NULL,
    used bigint NOT NULL CHECK (used >= 0),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, metric)
);

CREATE TABLE IF NOT EXISTS scenara_enterprise_records (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    record_type text NOT NULL CHECK (
        record_type IN ('incident', 'support_case', 'compliance_evidence')
    ),
    record_id text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, record_type, record_id)
);

CREATE INDEX IF NOT EXISTS scenara_enterprise_records_type_created_idx
    ON scenara_enterprise_records (tenant_id, project_id, record_type, created_at DESC);

CREATE TABLE IF NOT EXISTS scenara_audit_events (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    principal_id text NOT NULL,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    outcome text NOT NULL,
    request_id text,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scenara_feedback (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    feedback_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, feedback_id)
);

CREATE INDEX IF NOT EXISTS scenara_feedback_status_created_idx
    ON scenara_feedback (tenant_id, project_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS scenara_hard_sample_manifests (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    manifest_id text NOT NULL,
    dataset_id text NOT NULL,
    version text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, manifest_id),
    UNIQUE (tenant_id, project_id, dataset_id, version)
);

CREATE TABLE IF NOT EXISTS scenara_model_releases (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    model_id text NOT NULL,
    version text NOT NULL,
    status text NOT NULL CHECK (status IN ('candidate', 'validated', 'approved', 'active', 'retired')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, model_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS scenara_model_releases_one_active_idx
    ON scenara_model_releases (tenant_id, project_id, model_id)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS scenara_model_deployment_events (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    event_id text NOT NULL,
    model_id text NOT NULL,
    version text NOT NULL,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, event_id)
);

CREATE INDEX IF NOT EXISTS scenara_model_deployment_events_created_idx
    ON scenara_model_deployment_events (tenant_id, project_id, created_at DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0001_initial')
ON CONFLICT (version) DO NOTHING;

COMMIT;
