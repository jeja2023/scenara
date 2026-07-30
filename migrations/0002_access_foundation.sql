BEGIN;

CREATE TABLE IF NOT EXISTS scenara_organizations (
    tenant_id text PRIMARY KEY CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    display_name text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS scenara_projects (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    display_name text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id),
    FOREIGN KEY (tenant_id) REFERENCES scenara_organizations (tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_users (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    user_id text NOT NULL CHECK (user_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    display_name text NOT NULL,
    email text,
    disabled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES scenara_organizations (tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_roles (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    role_id text NOT NULL CHECK (role_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    display_name text NOT NULL,
    scopes text[] NOT NULL,
    product_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, role_id),
    FOREIGN KEY (tenant_id) REFERENCES scenara_organizations (tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_memberships (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    principal_id text NOT NULL CHECK (principal_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    principal_type text NOT NULL CHECK (principal_type IN ('user', 'service_account')),
    role_ids text[] NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, principal_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_service_accounts (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    service_account_id text NOT NULL CHECK (service_account_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    display_name text NOT NULL,
    scopes text[] NOT NULL,
    product_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
    disabled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, service_account_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scenara_api_keys (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    key_id text NOT NULL CHECK (key_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    service_account_id text NOT NULL,
    token_sha256 char(64) NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    token_prefix text NOT NULL,
    scopes text[] NOT NULL,
    product_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
    expires_at timestamptz,
    revoked_at timestamptz,
    last_used_at timestamptz,
    created_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, key_id),
    FOREIGN KEY (tenant_id, project_id, service_account_id)
        REFERENCES scenara_service_accounts (tenant_id, project_id, service_account_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS scenara_api_keys_service_account_idx
    ON scenara_api_keys (tenant_id, project_id, service_account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS scenara_product_entitlements (
    tenant_id text NOT NULL CHECK (tenant_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    project_id text NOT NULL CHECK (project_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    product_id text NOT NULL CHECK (product_id ~ '^[a-z][a-z0-9_.-]{1,63}$'),
    status text NOT NULL CHECK (status IN ('active', 'suspended')),
    source text NOT NULL CHECK (source IN ('manual', 'enterprise_license', 'system')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (tenant_id, project_id, product_id),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES scenara_projects (tenant_id, project_id) ON DELETE CASCADE
);

INSERT INTO scenara_schema_migrations (version)
VALUES ('0002_access_foundation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
