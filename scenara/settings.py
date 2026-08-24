from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


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


def _secret(name: str) -> str:
    """Load a secret from NAME or NAME_FILE without allowing ambiguous sources."""
    inline = os.getenv(name, "")
    file_name = os.getenv(f"{name}_FILE", "").strip()
    if inline and file_name:
        raise RuntimeError(f"{name} and {name}_FILE cannot both be configured")
    if not file_name:
        return inline.strip()
    path = Path(file_name)
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"{name}_FILE must reference a readable UTF-8 secret file") from exc
    if not value:
        raise RuntimeError(f"{name}_FILE must not be empty")
    return value


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


def _valid_fernet_key(value: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(value.encode("ascii"))) == 32
    except (ValueError, UnicodeError):
        return False


@dataclass(frozen=True, slots=True)
class Settings:
    profile: str
    state_backend: str
    object_backend: str
    queue_backend: str
    data_platform_mode: str
    data_platform_url: str
    data_platform_service_token: str
    data_event_service_token: str
    data_platform_timeout_seconds: float
    data_platform_max_retries: int
    data_dir: Path
    postgres_dsn: str
    redis_url: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_timeout_seconds: float
    qdrant_collection_prefix: str
    s3_endpoint_url: str
    s3_public_endpoint_url: str
    s3_region: str
    s3_bucket: str
    s3_access_key: str
    s3_secret_key: str
    s3_session_token: str
    s3_verify_tls: bool
    s3_ca_bundle: str
    s3_server_side_encryption: str
    s3_kms_key_id: str
    s3_multipart_threshold_bytes: int
    s3_multipart_chunk_bytes: int
    s3_lifecycle_enabled: bool
    s3_presigned_urls_enabled: bool
    s3_presign_expiry_seconds: int
    s3_addressing_style: str
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
    behavior_engine_factory: str
    fashion_engine_factory: str
    allowed_hosts: tuple[str, ...]
    hsts_enabled: bool
    hsts_max_age_seconds: int
    allow_insecure_internal_endpoints: bool
    run_artifacts_enabled: bool
    run_artifact_max_crops: int
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
        if self.data_platform_mode not in {"local", "http"}:
            raise RuntimeError("SCENARA_DATA_PLATFORM_MODE must be local or http")
        if self.data_platform_mode == "http" and not self.data_platform_url:
            raise RuntimeError("SCENARA_DATA_PLATFORM_URL is required when SCENARA_DATA_PLATFORM_MODE=http")
        if self.data_platform_timeout_seconds <= 0:
            raise RuntimeError("SCENARA_DATA_PLATFORM_TIMEOUT_SECONDS must be positive")
        if self.qdrant_url and self.qdrant_timeout_seconds <= 0:
            raise RuntimeError("SCENARA_QDRANT_TIMEOUT_SECONDS must be positive")
        if bool(self.s3_access_key) != bool(self.s3_secret_key):
            raise RuntimeError("SCENARA_S3_ACCESS_KEY and SCENARA_S3_SECRET_KEY must be configured together")
        if self.s3_session_token and not self.s3_access_key:
            raise RuntimeError("SCENARA_S3_SESSION_TOKEN requires explicit S3 access credentials")
        if self.s3_server_side_encryption not in {"", "AES256", "aws:kms"}:
            raise RuntimeError("SCENARA_S3_SERVER_SIDE_ENCRYPTION must be empty, AES256, or aws:kms")
        if self.s3_kms_key_id and self.s3_server_side_encryption != "aws:kms":
            raise RuntimeError("SCENARA_S3_KMS_KEY_ID requires aws:kms server-side encryption")
        if self.s3_ca_bundle and not Path(self.s3_ca_bundle).is_file():
            raise RuntimeError("SCENARA_S3_CA_BUNDLE must reference a readable CA bundle")
        if self.s3_addressing_style not in {"auto", "path", "virtual"}:
            raise RuntimeError("SCENARA_S3_ADDRESSING_STYLE must be auto, path, or virtual")
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
        if self.data_platform_mode != "http":
            errors.append("SCENARA_DATA_PLATFORM_MODE must be http")
        if not self.data_platform_url:
            errors.append("SCENARA_DATA_PLATFORM_URL is required")
        elif urlsplit(self.data_platform_url).scheme != "https" and not self.allow_insecure_internal_endpoints:
            errors.append("SCENARA_DATA_PLATFORM_URL must use HTTPS unless insecure internal endpoints are explicit")
        if not self.data_platform_service_token:
            errors.append("SCENARA_DATA_PLATFORM_SERVICE_TOKEN is required")
        if not self.data_event_service_token:
            errors.append("SCENARA_DATA_EVENT_SERVICE_TOKEN is required")
        if not self.postgres_dsn:
            errors.append("SCENARA_POSTGRES_DSN is required")
        if not self.redis_url:
            errors.append("SCENARA_REDIS_URL is required")
        if not self.s3_bucket:
            errors.append("SCENARA_S3_BUCKET is required")
        if not self.auth_required or not self.api_token:
            errors.append("production API authentication is required")
        elif len(self.api_token) < 32:
            errors.append("SCENARA_API_TOKEN must contain at least 32 characters")
        if self.data_platform_service_token and len(self.data_platform_service_token) < 24:
            errors.append("SCENARA_DATA_PLATFORM_SERVICE_TOKEN must contain at least 24 characters")
        if self.data_event_service_token and len(self.data_event_service_token) < 24:
            errors.append("SCENARA_DATA_EVENT_SERVICE_TOKEN must contain at least 24 characters")
        if self.data_platform_service_token == self.data_event_service_token:
            errors.append("Data request and event service tokens must be different")
        if not self.production_models_required:
            errors.append("SCENARA_PRODUCTION_MODELS_REQUIRED must be true")
        if self.production_models_required and not self.ocr_engine_factory:
            errors.append("SCENARA_OCR_ENGINE_FACTORY is required for the approved private OCR adapter")
        if self.production_models_required and not self.behavior_engine_factory:
            errors.append("SCENARA_BEHAVIOR_ENGINE_FACTORY is required for the approved private behavior adapter")
        if self.production_models_required and not self.fashion_engine_factory:
            errors.append("SCENARA_FASHION_ENGINE_FACTORY is required for the approved private fashion adapter")
        if not self.secret_encryption_key:
            errors.append("SCENARA_SECRET_ENCRYPTION_KEY is required")
        elif not _valid_fernet_key(self.secret_encryption_key):
            errors.append("SCENARA_SECRET_ENCRYPTION_KEY must be a valid Fernet key")
        if not self.allowed_hosts or "*" in self.allowed_hosts:
            errors.append("SCENARA_ALLOWED_HOSTS must explicitly list production hosts and cannot contain *")
        if self.bootstrap_admin_password and len(self.bootstrap_admin_password) < 16:
            errors.append("production bootstrap administrator password must contain at least 16 characters")
        if (self.enterprise_license_path is None) != (self.enterprise_public_key_path is None):
            errors.append("enterprise license and public key paths must be configured together")
        if errors:
            raise RuntimeError("invalid Scenara production configuration: " + "; ".join(errors))


def load_settings() -> Settings:
    profile = os.getenv("SCENARA_PROFILE", "development").strip().lower()
    settings = Settings(
        profile=profile,
        state_backend=os.getenv("SCENARA_STATE_BACKEND", "memory").strip().lower(),
        object_backend=os.getenv("SCENARA_OBJECT_BACKEND", "local").strip().lower(),
        queue_backend=os.getenv("SCENARA_QUEUE_BACKEND", "inline").strip().lower(),
        data_platform_mode=os.getenv("SCENARA_DATA_PLATFORM_MODE", "local").strip().lower(),
        data_platform_url=os.getenv("SCENARA_DATA_PLATFORM_URL", "").strip().rstrip("/"),
        data_platform_service_token=_secret("SCENARA_DATA_PLATFORM_SERVICE_TOKEN"),
        data_event_service_token=_secret("SCENARA_DATA_EVENT_SERVICE_TOKEN")
        or _secret("SCENARA_DATA_PLATFORM_SERVICE_TOKEN"),
        data_platform_timeout_seconds=max(0.1, float(os.getenv("SCENARA_DATA_PLATFORM_TIMEOUT_SECONDS", "10"))),
        data_platform_max_retries=max(0, min(5, int(os.getenv("SCENARA_DATA_PLATFORM_MAX_RETRIES", "2")))),
        data_dir=Path(os.getenv("SCENARA_DATA_DIR", "runtime-state")).resolve(),
        postgres_dsn=_secret("SCENARA_POSTGRES_DSN"),
        redis_url=_secret("SCENARA_REDIS_URL"),
        qdrant_url=os.getenv("SCENARA_QDRANT_URL", "").strip().rstrip("/"),
        qdrant_api_key=_secret("SCENARA_QDRANT_API_KEY"),
        qdrant_timeout_seconds=max(0.1, float(os.getenv("SCENARA_QDRANT_TIMEOUT_SECONDS", "10"))),
        qdrant_collection_prefix=os.getenv("SCENARA_QDRANT_COLLECTION_PREFIX", "scenara_features").strip()
        or "scenara_features",
        s3_endpoint_url=os.getenv("SCENARA_S3_ENDPOINT_URL", "").strip(),
        s3_public_endpoint_url=os.getenv("SCENARA_S3_PUBLIC_ENDPOINT_URL", "").strip(),
        s3_region=os.getenv("SCENARA_S3_REGION", "us-east-1").strip(),
        s3_bucket=os.getenv("SCENARA_S3_BUCKET", "").strip(),
        s3_access_key=_secret("SCENARA_S3_ACCESS_KEY"),
        s3_secret_key=_secret("SCENARA_S3_SECRET_KEY"),
        s3_session_token=_secret("SCENARA_S3_SESSION_TOKEN"),
        s3_verify_tls=_bool("SCENARA_S3_VERIFY_TLS", True),
        s3_ca_bundle=os.getenv("SCENARA_S3_CA_BUNDLE", "").strip(),
        s3_server_side_encryption=os.getenv("SCENARA_S3_SERVER_SIDE_ENCRYPTION", "").strip(),
        s3_kms_key_id=os.getenv("SCENARA_S3_KMS_KEY_ID", "").strip(),
        s3_multipart_threshold_bytes=max(
            5 * 1024 * 1024,
            int(os.getenv("SCENARA_S3_MULTIPART_THRESHOLD_BYTES", str(64 * 1024 * 1024))),
        ),
        s3_multipart_chunk_bytes=max(
            5 * 1024 * 1024,
            int(os.getenv("SCENARA_S3_MULTIPART_CHUNK_BYTES", str(16 * 1024 * 1024))),
        ),
        s3_lifecycle_enabled=_bool("SCENARA_S3_LIFECYCLE_ENABLED", False),
        s3_presigned_urls_enabled=_bool("SCENARA_S3_PRESIGNED_URLS_ENABLED", False),
        s3_presign_expiry_seconds=max(
            60,
            min(86_400, int(os.getenv("SCENARA_S3_PRESIGN_EXPIRY_SECONDS", "900"))),
        ),
        s3_addressing_style=os.getenv("SCENARA_S3_ADDRESSING_STYLE", "auto").strip().lower(),
        api_token=_secret("SCENARA_API_TOKEN"),
        auth_required=_bool("SCENARA_AUTH_REQUIRED", profile in {"prod", "production"}),
        default_tenant_id=os.getenv("SCENARA_DEFAULT_TENANT_ID", "default").strip(),
        default_project_id=os.getenv("SCENARA_DEFAULT_PROJECT_ID", "default").strip(),
        bootstrap_admin_username=os.getenv("SCENARA_BOOTSTRAP_ADMIN_USERNAME", "").strip(),
        bootstrap_admin_password=_secret("SCENARA_BOOTSTRAP_ADMIN_PASSWORD"),
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
        secret_encryption_key=_secret("SCENARA_SECRET_ENCRYPTION_KEY"),
        enterprise_policy_required=_bool("SCENARA_ENTERPRISE_POLICY_REQUIRED", False),
        allow_private_media_sources=_bool("SCENARA_ALLOW_PRIVATE_MEDIA_SOURCES", False),
        allow_private_webhook_targets=_bool("SCENARA_ALLOW_PRIVATE_WEBHOOK_TARGETS", False),
        ocr_engine_factory=os.getenv("SCENARA_OCR_ENGINE_FACTORY", "").strip(),
        behavior_engine_factory=os.getenv("SCENARA_BEHAVIOR_ENGINE_FACTORY", "").strip(),
        fashion_engine_factory=os.getenv("SCENARA_FASHION_ENGINE_FACTORY", "").strip(),
        allowed_hosts=_csv("SCENARA_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,test,core"),
        hsts_enabled=_bool("SCENARA_HSTS_ENABLED", profile in {"prod", "production"}),
        hsts_max_age_seconds=max(
            0,
            min(63_072_000, int(os.getenv("SCENARA_HSTS_MAX_AGE_SECONDS", "31536000"))),
        ),
        allow_insecure_internal_endpoints=_bool("SCENARA_ALLOW_INSECURE_INTERNAL_ENDPOINTS", False),
        run_artifacts_enabled=_bool("SCENARA_RUN_ARTIFACTS_ENABLED", True),
        run_artifact_max_crops=max(0, min(5_000, int(os.getenv("SCENARA_RUN_ARTIFACT_MAX_CROPS", "200")))),
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
