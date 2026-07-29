from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    profile: str
    state_backend: str
    object_backend: str
    queue_backend: str
    data_dir: Path
    postgres_dsn: str
    redis_url: str
    s3_endpoint_url: str
    s3_region: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    api_token: str
    auth_required: bool
    default_tenant_id: str
    default_project_id: str
    max_image_bytes: int
    image_wait_timeout_ms: int
    production_models_required: bool

    @property
    def production(self) -> bool:
        return self.profile in {"prod", "production"}

    def validate(self) -> None:
        if not self.production:
            return
        errors: list[str] = []
        if self.state_backend != "postgres":
            errors.append("SCENARA_STATE_BACKEND must be postgres")
        if self.object_backend != "s3":
            errors.append("SCENARA_OBJECT_BACKEND must be s3")
        if self.queue_backend != "redis":
            errors.append("SCENARA_QUEUE_BACKEND must be redis")
        if not self.postgres_dsn:
            errors.append("SCENARA_POSTGRES_DSN is required")
        if not self.redis_url:
            errors.append("SCENARA_REDIS_URL is required")
        if not self.s3_bucket:
            errors.append("SCENARA_S3_BUCKET is required")
        if not self.auth_required or not self.api_token:
            errors.append("production API authentication is required")
        if not self.production_models_required:
            errors.append("SCENARA_PRODUCTION_MODELS_REQUIRED must be true")
        if errors:
            raise RuntimeError("invalid Scenara production configuration: " + "; ".join(errors))


def load_settings() -> Settings:
    profile = os.getenv("SCENARA_PROFILE", "development").strip().lower()
    settings = Settings(
        profile=profile,
        state_backend=os.getenv("SCENARA_STATE_BACKEND", "memory").strip().lower(),
        object_backend=os.getenv("SCENARA_OBJECT_BACKEND", "local").strip().lower(),
        queue_backend=os.getenv("SCENARA_QUEUE_BACKEND", "inline").strip().lower(),
        data_dir=Path(os.getenv("SCENARA_DATA_DIR", "runtime-state")).resolve(),
        postgres_dsn=os.getenv("SCENARA_POSTGRES_DSN", "").strip(),
        redis_url=os.getenv("SCENARA_REDIS_URL", "").strip(),
        s3_endpoint_url=os.getenv("SCENARA_S3_ENDPOINT_URL", "").strip(),
        s3_region=os.getenv("SCENARA_S3_REGION", "us-east-1").strip(),
        s3_bucket=os.getenv("SCENARA_S3_BUCKET", "").strip(),
        s3_access_key=os.getenv("SCENARA_S3_ACCESS_KEY", "").strip(),
        s3_secret_key=os.getenv("SCENARA_S3_SECRET_KEY", "").strip(),
        api_token=os.getenv("SCENARA_API_TOKEN", "").strip(),
        auth_required=_bool("SCENARA_AUTH_REQUIRED", profile in {"prod", "production"}),
        default_tenant_id=os.getenv("SCENARA_DEFAULT_TENANT_ID", "default").strip(),
        default_project_id=os.getenv("SCENARA_DEFAULT_PROJECT_ID", "default").strip(),
        max_image_bytes=max(1, int(os.getenv("SCENARA_MAX_IMAGE_BYTES", str(25 * 1024 * 1024)))),
        image_wait_timeout_ms=max(0, min(30_000, int(os.getenv("SCENARA_IMAGE_WAIT_TIMEOUT_MS", "10000")))),
        production_models_required=_bool("SCENARA_PRODUCTION_MODELS_REQUIRED", False),
    )
    settings.validate()
    return settings
