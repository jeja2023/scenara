from __future__ import annotations

from pathlib import Path

from app.runtime_defaults import local_dev_env_overrides
from scripts.prepare_runtime_state import prepare_runtime_state


def test_local_rollout_audit_is_under_runtime_logs(tmp_path: Path) -> None:
    overrides = local_dev_env_overrides(tmp_path)

    assert Path(overrides["ROLLOUT_AUDIT_PATH"]) == tmp_path / "runtime-state" / "logs" / "rollout-audit.jsonl"


def test_prepare_runtime_state_creates_managed_directories(tmp_path: Path) -> None:
    paths = prepare_runtime_state(tmp_path / "runtime-state")

    assert all(path.is_dir() for path in paths)
    assert (tmp_path / "runtime-state" / "logs").is_dir()
