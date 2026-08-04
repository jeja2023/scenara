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
