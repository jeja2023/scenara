from __future__ import annotations

import base64

from scripts.generate_production_env import render
from scripts.validate_production_config import validate


def valid_values() -> dict[str, str]:
    return {
        "SCENARA_POSTGRES_PASSWORD": "example-postgres-password-0123456789",
        "SCENARA_REDIS_PASSWORD": "example-redis-password-0123456789012",
        "SCENARA_MINIO_ROOT_USER": "scenara-root",
        "SCENARA_MINIO_ROOT_PASSWORD": "example-minio-root-password-012345678",
        "SCENARA_S3_ACCESS_KEY": "scenara-app",
        "SCENARA_S3_SECRET_KEY": "example-s3-app-password-012345678901",
        "SCENARA_DATA_PLATFORM_URL": "https://data.internal.example",
        "SCENARA_DATA_PLATFORM_SERVICE_TOKEN": "example-data-request-token-0123456789",
        "SCENARA_DATA_EVENT_SERVICE_TOKEN": "example-data-event-token-012345678901",
        "SCENARA_API_TOKEN": "example-api-bootstrap-token-012345678901",
        "SCENARA_SECRET_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"f" * 32).decode("ascii"),
        "SCENARA_OCR_ENGINE_FACTORY": "approved.ocr:create_engine",
        "SCENARA_BEHAVIOR_ENGINE_FACTORY": "approved.behavior:create_engine",
        "SCENARA_FASHION_ENGINE_FACTORY": "approved.fashion:create_engine",
        "SCENARA_ALLOWED_HOSTS": "scenara.example.com",
        "SCENARA_FORWARDED_ALLOW_IPS": "10.0.0.10",
        "SCENARA_AUTH_REQUIRED": "true",
        "SCENARA_PRODUCTION_MODELS_REQUIRED": "true",
        "SCENARA_IMAGE_REFERENCE": "registry.example/scenara@sha256:" + "a" * 64,
        "SCENARA_BIND_ADDRESS": "127.0.0.1",
        "SCENARA_RAW_MEDIA_RETENTION_DAYS": "7",
        "SCENARA_PREVIEW_RETENTION_DAYS": "30",
        "SCENARA_STRUCTURED_RESULT_RETENTION_DAYS": "180",
    }


def test_valid_production_configuration_passes_without_exposing_secrets() -> None:
    errors, warnings = validate(valid_values(), file_mode=True)
    assert errors == []
    assert warnings == []


def test_production_configuration_rejects_placeholders_reuse_and_unsafe_networks() -> None:
    values = valid_values()
    values["SCENARA_API_TOKEN"] = "replace-with-token"
    values["SCENARA_DATA_EVENT_SERVICE_TOKEN"] = values["SCENARA_DATA_PLATFORM_SERVICE_TOKEN"]
    values["SCENARA_ALLOWED_HOSTS"] = "*"
    values["SCENARA_FORWARDED_ALLOW_IPS"] = "*"
    values["SCENARA_DATA_PLATFORM_URL"] = "http://data.internal"
    values["SCENARA_OCR_ENGINE_FACTORY"] = "scenara.domains.ocr.paddle_reference_adapter:create_reference_ocr_engine"
    errors, _ = validate(values, file_mode=True)
    joined = "\n".join(errors)
    assert "placeholder" in joined
    assert "must not be reused" in joined
    assert "ALLOWED_HOSTS" in joined
    assert "FORWARDED_ALLOW_IPS" in joined
    assert "must use HTTPS" in joined
    assert "unqualified built-in" in joined


def test_production_configuration_rejects_invalid_upload_and_database_capacity_bounds() -> None:
    values = valid_values()
    values["SCENARA_MAX_MEDIA_BYTES"] = "100"
    values["SCENARA_MAX_MULTIPART_UPLOAD_BYTES"] = "101"
    values["SCENARA_POSTGRES_POOL_MIN_SIZE"] = "3"
    values["SCENARA_POSTGRES_POOL_MAX_SIZE"] = "2"
    errors, _ = validate(values, file_mode=True)
    joined = "\n".join(errors)
    assert "MULTIPART_UPLOAD_BYTES cannot exceed" in joined
    assert "POOL_MAX_SIZE must be at least" in joined


def test_generated_candidate_replaces_every_generated_secret_placeholder() -> None:
    candidate = render()
    for placeholder in (
        "replace-with-postgres-password",
        "replace-with-redis-password",
        "replace-with-minio-root-password",
        "replace-with-s3-secret-key",
        "replace-with-core-to-data-service-token",
        "replace-with-data-to-core-service-token",
        "replace-with-long-random-bootstrap-token",
        "replace-with-generated-fernet-key",
        "replace-with-admin-password-16chars",
    ):
        assert placeholder not in candidate
    assert "SCENARA_IMAGE_REFERENCE=scenara-api@sha256:replace-with-" in candidate
    assert "SCENARA_FORWARDED_ALLOW_IPS=replace-with-" in candidate
