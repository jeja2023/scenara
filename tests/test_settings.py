from __future__ import annotations

from dataclasses import replace

import pytest

from scenara.settings import load_settings


def test_production_rejects_development_backends() -> None:
    settings = replace(load_settings(), profile="production")
    with pytest.raises(RuntimeError, match="STATE_BACKEND"):
        settings.validate()
