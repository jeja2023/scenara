from __future__ import annotations

from dataclasses import replace
import base64

import pytest

from scenara.settings import load_settings


def test_production_rejects_development_backends() -> None:
    settings = replace(load_settings(), profile="production")
    with pytest.raises(RuntimeError, match="STATE_BACKEND"):
        settings.validate()


def test_bootstrap_admin_requires_a_complete_strong_credential_pair() -> None:
    with pytest.raises(RuntimeError, match="must be configured together"):
        replace(load_settings(), bootstrap_admin_username="admin").validate()
    with pytest.raises(RuntimeError, match="at least 12 characters"):
        replace(
            load_settings(),
            bootstrap_admin_username="admin",
            bootstrap_admin_password="too-short",
        ).validate()


def test_s3_credentials_can_use_default_provider_chain() -> None:
    replace(
        load_settings(),
        s3_access_key="",
        s3_secret_key="",
        s3_session_token="",
    ).validate()


def test_s3_security_configuration_rejects_partial_or_invalid_values(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="ACCESS_KEY"):
        replace(load_settings(), s3_access_key="only-one", s3_secret_key="").validate()
    with pytest.raises(RuntimeError, match="SESSION_TOKEN"):
        replace(
            load_settings(),
            s3_access_key="",
            s3_secret_key="",
            s3_session_token="temporary-token",
        ).validate()
    with pytest.raises(RuntimeError, match="KMS_KEY_ID"):
        replace(
            load_settings(),
            s3_server_side_encryption="AES256",
            s3_kms_key_id="alias/scenara",
        ).validate()
    with pytest.raises(RuntimeError, match="CA_BUNDLE"):
        replace(load_settings(), s3_ca_bundle=str(tmp_path / "missing.pem")).validate()
    with pytest.raises(RuntimeError, match="ADDRESSING_STYLE"):
        replace(load_settings(), s3_addressing_style="unsupported").validate()


def test_production_security_boundary_requires_strong_distinct_secrets() -> None:
    fernet_key = base64.urlsafe_b64encode(b"x" * 32).decode("ascii")
    settings = replace(
        load_settings(),
        profile="production",
        state_backend="postgres",
        object_backend="s3",
        queue_backend="redis",
        data_platform_mode="http",
        data_platform_url="http://scenara-data:8010",
        allow_insecure_internal_endpoints=True,
        data_platform_service_token="example-request-token-0123456789012345",
        data_event_service_token="example-event-token-012345678901234567",
        postgres_dsn="postgresql://scenara@postgres/scenara",
        redis_url="redis://:secret@redis:6379/0",
        s3_bucket="scenara",
        auth_required=True,
        api_token="example-api-token-012345678901234567890123",
        production_models_required=True,
        ocr_engine_factory="approved.ocr:create",
        behavior_engine_factory="approved.behavior:create",
        fashion_engine_factory="approved.fashion:create",
        secret_encryption_key=fernet_key,
        allowed_hosts=("scenara.example.com",),
    )
    settings.validate()
    with pytest.raises(RuntimeError, match="must be different"):
        replace(settings, data_event_service_token=settings.data_platform_service_token).validate()
    with pytest.raises(RuntimeError, match="Fernet"):
        replace(settings, secret_encryption_key="not-a-fernet-key").validate()
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        replace(settings, allowed_hosts=("*",)).validate()


def test_secret_file_loading_and_ambiguous_source_rejection(tmp_path, monkeypatch) -> None:
    secret_file = tmp_path / "api-token"
    secret_file.write_text("file-backed-secret-value", encoding="utf-8")
    monkeypatch.delenv("SCENARA_API_TOKEN", raising=False)
    monkeypatch.setenv("SCENARA_API_TOKEN_FILE", str(secret_file))
    assert load_settings().api_token == "file-backed-secret-value"
    monkeypatch.setenv("SCENARA_API_TOKEN", "inline-secret")
    with pytest.raises(RuntimeError, match="cannot both"):
        load_settings()
