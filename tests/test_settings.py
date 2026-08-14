from __future__ import annotations

from dataclasses import replace

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
