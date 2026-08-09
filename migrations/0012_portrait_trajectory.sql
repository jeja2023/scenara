BEGIN;

CREATE TABLE IF NOT EXISTS scenara_trajectory_cameras (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    camera_id text NOT NULL CHECK (camera_id ~ '^[A-Za-z0-9_.:-]{1,128}$'),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, camera_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_trajectory_camera_transitions (
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    from_camera_id text NOT NULL,
    to_camera_id text NOT NULL,
    min_seconds double precision NOT NULL DEFAULT 0 CHECK (min_seconds >= 0),
    max_seconds double precision CHECK (max_seconds IS NULL OR max_seconds >= 0),
    PRIMARY KEY (tenant_id, project_id, from_camera_id, to_camera_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_trajectory_identities (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    identity_id text NOT NULL CHECK (identity_id ~ '^[A-Za-z0-9_.:-]{2,160}$'),
    status text NOT NULL CHECK (status IN ('auto', 'confirmed', 'rejected')),
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, identity_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_trajectory_identity_scope_idx
    ON scenara_trajectory_identities (tenant_id, project_id, status, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS scenara_trajectory_segments (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    segment_id text NOT NULL CHECK (segment_id ~ '^[A-Za-z0-9_.:-]{2,160}$'),
    identity_id text NOT NULL,
    camera_id text NOT NULL DEFAULT '',
    run_id text NOT NULL DEFAULT '',
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, segment_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_trajectory_segment_identity_idx
    ON scenara_trajectory_segments (tenant_id, project_id, identity_id, first_seen_at DESC);

CREATE INDEX IF NOT EXISTS scenara_trajectory_segment_camera_idx
    ON scenara_trajectory_segments (tenant_id, project_id, camera_id, first_seen_at DESC);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0012_portrait_trajectory')
ON CONFLICT (version) DO NOTHING;

COMMIT;
