BEGIN;

CREATE TABLE IF NOT EXISTS scenara_surveillance_watchlists (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    watchlist_id text NOT NULL CHECK (watchlist_id ~ '^[A-Za-z0-9_.:-]{2,128}$'),
    status text NOT NULL CHECK (status IN ('active', 'paused', 'archived')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, watchlist_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_watchlists_scope_idx
    ON scenara_surveillance_watchlists (tenant_id, project_id, updated_at DESC, watchlist_id);

CREATE TABLE IF NOT EXISTS scenara_surveillance_watchlist_members (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    member_id text NOT NULL CHECK (member_id ~ '^[A-Za-z0-9_.:-]{2,128}$'),
    watchlist_id text NOT NULL,
    portrait_identity_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('active', 'paused', 'removed')),
    valid_from timestamptz,
    valid_until timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, member_id),
    UNIQUE (tenant_id, project_id, watchlist_id, portrait_identity_id),
    CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from),
    FOREIGN KEY (tenant_id, project_id, watchlist_id)
        REFERENCES scenara_surveillance_watchlists (tenant_id, project_id, watchlist_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, portrait_identity_id)
        REFERENCES scenara_portrait_identities (tenant_id, project_id, identity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_members_active_idx
    ON scenara_surveillance_watchlist_members
       (tenant_id, project_id, watchlist_id, status, valid_from, valid_until, member_id);

CREATE TABLE IF NOT EXISTS scenara_surveillance_tasks (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    task_id text NOT NULL CHECK (task_id ~ '^[A-Za-z0-9_.:-]{2,128}$'),
    status text NOT NULL CHECK (status IN ('draft', 'active', 'paused', 'expired', 'failed')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, task_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_tasks_scope_idx
    ON scenara_surveillance_tasks (tenant_id, project_id, status, updated_at DESC, task_id);

CREATE TABLE IF NOT EXISTS scenara_surveillance_task_bindings (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    binding_id text NOT NULL CHECK (binding_id ~ '^[A-Za-z0-9_.:-]{2,128}$'),
    task_id text NOT NULL,
    source_id text NOT NULL,
    camera_id text NOT NULL,
    active_run_id text,
    stream_session_id text,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, binding_id),
    UNIQUE (tenant_id, project_id, task_id, source_id, camera_id),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES scenara_surveillance_tasks (tenant_id, project_id, task_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES scenara_media_sources (tenant_id, project_id, source_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, project_id, camera_id)
        REFERENCES scenara_trajectory_cameras (tenant_id, project_id, camera_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_bindings_source_idx
    ON scenara_surveillance_task_bindings (tenant_id, project_id, source_id, task_id);

CREATE TABLE IF NOT EXISTS scenara_surveillance_alerts (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    alert_id text NOT NULL CHECK (alert_id ~ '^[A-Za-z0-9_.:-]{2,128}$'),
    task_id text NOT NULL,
    binding_id text NOT NULL,
    watchlist_id text NOT NULL,
    member_id text NOT NULL,
    portrait_identity_id text NOT NULL,
    camera_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'confirmed', 'false_positive', 'ignored')),
    triggered_at timestamptz NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    match_score double precision NOT NULL CHECK (match_score BETWEEN -1 AND 1),
    max_score double precision NOT NULL CHECK (max_score BETWEEN -1 AND 1),
    occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    idempotency_key text NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, alert_id),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES scenara_surveillance_tasks (tenant_id, project_id, task_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_alerts_scope_time_idx
    ON scenara_surveillance_alerts (tenant_id, project_id, triggered_at DESC, alert_id);
CREATE INDEX IF NOT EXISTS scenara_surveillance_alerts_filter_idx
    ON scenara_surveillance_alerts
       (tenant_id, project_id, status, task_id, camera_id, watchlist_id, portrait_identity_id, triggered_at DESC);

CREATE TABLE IF NOT EXISTS scenara_surveillance_alert_events (
    event_cursor bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id text NOT NULL UNIQUE CHECK (event_id ~ '^[A-Za-z0-9_.:-]{2,128}$'),
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    alert_id text NOT NULL,
    event_type text NOT NULL CHECK (event_type IN ('alert.triggered', 'alert.triaged')),
    occurred_at text NOT NULL,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    FOREIGN KEY (tenant_id, project_id, alert_id)
        REFERENCES scenara_surveillance_alerts (tenant_id, project_id, alert_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_alert_events_replay_idx
    ON scenara_surveillance_alert_events (tenant_id, project_id, event_cursor);

CREATE TABLE IF NOT EXISTS scenara_surveillance_debounce (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    debounce_key text NOT NULL,
    task_id text NOT NULL,
    binding_id text NOT NULL,
    watchlist_id text NOT NULL,
    portrait_identity_id text NOT NULL,
    cooldown_until timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    max_score double precision NOT NULL CHECK (max_score BETWEEN -1 AND 1),
    occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
    revision integer NOT NULL CHECK (revision > 0),
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, debounce_key),
    FOREIGN KEY (tenant_id, project_id, task_id)
        REFERENCES scenara_surveillance_tasks (tenant_id, project_id, task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_surveillance_debounce_expiry_idx
    ON scenara_surveillance_debounce (cooldown_until, last_seen_at);

ALTER TABLE scenara_object_retention
    DROP CONSTRAINT IF EXISTS scenara_object_retention_category_check;
ALTER TABLE scenara_object_retention
    ADD CONSTRAINT scenara_object_retention_category_check
    CHECK (category IN ('raw_media', 'preview', 'structured_result', 'biometric', 'alert_snapshot'));
ALTER TABLE scenara_object_retention
    DROP CONSTRAINT IF EXISTS scenara_object_retention_owner_type_check;
ALTER TABLE scenara_object_retention
    ADD CONSTRAINT scenara_object_retention_owner_type_check
    CHECK (owner_type IN ('media_asset', 'run_result', 'portrait_enrollment', 'surveillance_alert'));

INSERT INTO scenara_schema_migrations (version)
VALUES ('0014_surveillance_alerts')
ON CONFLICT (version) DO NOTHING;

COMMIT;
