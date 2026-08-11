from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ratio(name: str, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return max(minimum, min(maximum, float(raw)))


def _optional_path(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    return Path(raw).resolve() if raw else None


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
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    max_image_bytes: int
    max_media_bytes: int
    media_sample_interval_ms: int
    stream_segment_duration_ms: int
    enterprise_license_path: Path | None
    enterprise_public_key_path: Path | None
    result_shard_units: int
    image_wait_timeout_ms: int
    production_models_required: bool
    secret_encryption_key: str
    enterprise_policy_required: bool
    raw_media_retention_days: int
    preview_retention_days: int
    structured_result_retention_days: int
    allow_private_media_sources: bool
    allow_private_webhook_targets: bool
    ocr_engine_factory: str
    run_artifacts_enabled: bool
    run_artifact_max_crops: int
    run_artifact_max_frames: int
    run_artifact_crop_max_edge: int
    run_artifact_frame_max_edge: int
    trajectory_enabled: bool
    trajectory_body_threshold: float
    trajectory_face_threshold: float
    trajectory_min_track_quality: float
    trajectory_min_frame_count: int
    trajectory_max_templates: int
    trajectory_default_transition_seconds: float

    @property
    def production(self) -> bool:
        return self.profile in {"prod", "production"}

    def validate(self) -> None:
        if bool(self.bootstrap_admin_username) != bool(self.bootstrap_admin_password):
            raise RuntimeError(
                "SCENARA_BOOTSTRAP_ADMIN_USERNAME and SCENARA_BOOTSTRAP_ADMIN_PASSWORD must be configured together"
            )
        if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 12:
            raise RuntimeError("SCENARA_BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
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
        if self.production_models_required and not self.ocr_engine_factory:
            errors.append("SCENARA_OCR_ENGINE_FACTORY is required for the approved private OCR adapter")
        if not self.secret_encryption_key:
            errors.append("SCENARA_SECRET_ENCRYPTION_KEY is required")
        if not self.enterprise_policy_required:
            errors.append("SCENARA_ENTERPRISE_POLICY_REQUIRED must be true")
        if self.enterprise_policy_required and (
            self.enterprise_license_path is None or self.enterprise_public_key_path is None
        ):
            errors.append("enterprise policy requires license and public key paths")
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
        bootstrap_admin_username=os.getenv("SCENARA_BOOTSTRAP_ADMIN_USERNAME", "").strip(),
        bootstrap_admin_password=os.getenv("SCENARA_BOOTSTRAP_ADMIN_PASSWORD", ""),
        max_image_bytes=max(1, int(os.getenv("SCENARA_MAX_IMAGE_BYTES", str(25 * 1024 * 1024)))),
        max_media_bytes=max(1, int(os.getenv("SCENARA_MAX_MEDIA_BYTES", str(20 * 1024 * 1024 * 1024)))),
        media_sample_interval_ms=max(
            1,
            min(3_600_000, int(os.getenv("SCENARA_MEDIA_SAMPLE_INTERVAL_MS", "1000"))),
        ),
        stream_segment_duration_ms=max(
            1_000,
            min(86_400_000, int(os.getenv("SCENARA_STREAM_SEGMENT_DURATION_MS", "300000"))),
        ),
        result_shard_units=max(1, min(10_000, int(os.getenv("SCENARA_RESULT_SHARD_UNITS", "100")))),
        image_wait_timeout_ms=max(0, min(30_000, int(os.getenv("SCENARA_IMAGE_WAIT_TIMEOUT_MS", "10000")))),
        production_models_required=_bool("SCENARA_PRODUCTION_MODELS_REQUIRED", False),
        secret_encryption_key=os.getenv("SCENARA_SECRET_ENCRYPTION_KEY", "").strip(),
        enterprise_policy_required=_bool("SCENARA_ENTERPRISE_POLICY_REQUIRED", False),
        allow_private_media_sources=_bool("SCENARA_ALLOW_PRIVATE_MEDIA_SOURCES", False),
        allow_private_webhook_targets=_bool("SCENARA_ALLOW_PRIVATE_WEBHOOK_TARGETS", False),
        ocr_engine_factory=os.getenv("SCENARA_OCR_ENGINE_FACTORY", "").strip(),
        run_artifacts_enabled=_bool("SCENARA_RUN_ARTIFACTS_ENABLED", True),
        run_artifact_max_crops=max(0, min(5_000, int(os.getenv("SCENARA_RUN_ARTIFACT_MAX_CROPS", "200")))),
        run_artifact_max_frames=max(0, min(1_000, int(os.getenv("SCENARA_RUN_ARTIFACT_MAX_FRAMES", "64")))),
        run_artifact_crop_max_edge=max(
            32,
            min(2_048, int(os.getenv("SCENARA_RUN_ARTIFACT_CROP_MAX_EDGE", "256"))),
        ),
        run_artifact_frame_max_edge=max(
            64,
            min(8_192, int(os.getenv("SCENARA_RUN_ARTIFACT_FRAME_MAX_EDGE", "1920"))),
        ),
        enterprise_license_path=_optional_path("SCENARA_ENTERPRISE_LICENSE_PATH"),
        enterprise_public_key_path=_optional_path("SCENARA_ENTERPRISE_PUBLIC_KEY_PATH"),
        raw_media_retention_days=max(1, min(3650, int(os.getenv("SCENARA_RAW_MEDIA_RETENTION_DAYS", "7")))),
        preview_retention_days=max(1, min(3650, int(os.getenv("SCENARA_PREVIEW_RETENTION_DAYS", "30")))),
        structured_result_retention_days=max(
            1,
            min(3650, int(os.getenv("SCENARA_STRUCTURED_RESULT_RETENTION_DAYS", "180"))),
        ),
        trajectory_enabled=_bool("SCENARA_TRAJECTORY_ENABLED", True),
        trajectory_body_threshold=_ratio("SCENARA_TRAJECTORY_BODY_THRESHOLD", 0.72, minimum=-1.0),
        trajectory_face_threshold=_ratio("SCENARA_TRAJECTORY_FACE_THRESHOLD", 0.80, minimum=-1.0),
        trajectory_min_track_quality=_ratio("SCENARA_TRAJECTORY_MIN_TRACK_QUALITY", 0.35),
        trajectory_min_frame_count=max(1, min(10_000, int(os.getenv("SCENARA_TRAJECTORY_MIN_FRAME_COUNT", "2")))),
        trajectory_max_templates=max(1, min(1_000, int(os.getenv("SCENARA_TRAJECTORY_MAX_TEMPLATES", "32")))),
        trajectory_default_transition_seconds=_ratio(
            "SCENARA_TRAJECTORY_DEFAULT_TRANSITION_SECONDS", 0.0, maximum=86_400.0
        ),
    )
    settings.validate()
    return settings
