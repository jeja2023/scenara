BEGIN;

CREATE TABLE IF NOT EXISTS scenara_user_credentials (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    user_id text NOT NULL CHECK (user_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES scenara_users (tenant_id, user_id) ON DELETE CASCADE
);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0010_user_credentials')
ON CONFLICT (version) DO NOTHING;

COMMIT;
