from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_CALL = re.compile(
    r'(?:os\.getenv|_bool|_ratio|_optional_path)\("(SCENARA_[A-Z0-9_]+)"'
)
ENV_ASSIGNMENT = re.compile(r"(?m)^(SCENARA_[A-Z0-9_]+)=")


def test_env_example_covers_every_runtime_setting_once() -> None:
    settings_source = (ROOT / "scenara/settings.py").read_text(encoding="utf-8")
    template = (ROOT / ".env.example").read_text(encoding="utf-8")
    runtime_names = set(ENV_CALL.findall(settings_source))
    assignments = ENV_ASSIGNMENT.findall(template)

    assert runtime_names <= set(assignments)
    assert len(assignments) == len(set(assignments))
    assert "SCENARA_MAX_MEDIA_UNITS" not in assignments
