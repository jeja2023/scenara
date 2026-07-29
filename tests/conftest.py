from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scenara.settings import load_settings


@pytest.fixture
def development_settings(tmp_path: Path):
    return replace(
        load_settings(),
        profile="test",
        state_backend="memory",
        object_backend="local",
        data_dir=tmp_path,
        auth_required=False,
        image_wait_timeout_ms=2_000,
    )
