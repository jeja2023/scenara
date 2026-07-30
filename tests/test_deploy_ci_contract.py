from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "compose.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BACKUP_SCRIPT = ROOT / "deploy" / "scripts" / "backup.sh"
RESTORE_SCRIPT = ROOT / "deploy" / "scripts" / "restore.sh"
REQUIRED_VARIABLE = re.compile(r"\$\{(SCENARA_[A-Z0-9_]+):\?")
NODE24_ACTION_MAJORS = {
    "actions/checkout": 7,
    "actions/setup-node": 7,
    "actions/setup-python": 7,
    "actions/upload-artifact": 7,
    "pnpm/action-setup": 6,
}


def required_compose_variables() -> set[str]:
    return set(REQUIRED_VARIABLE.findall(COMPOSE.read_text(encoding="utf-8")))


def compose_jobs() -> dict[str, dict[str, object]]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = document["jobs"]
    return {
        name: job
        for name, job in jobs.items()
        if "deploy/compose.yml" in yaml.dump(job)
    }


def provided_variables(job: dict[str, object]) -> set[str]:
    env = job.get("env") or {}
    provided = {str(name) for name in env}
    for step in job.get("steps") or []:
        step_env = step.get("env") or {}
        provided.update(str(name) for name in step_env)
        body = yaml.dump(step)
        provided.update(re.findall(r"^\s*(SCENARA_[A-Z0-9_]+)=", body, re.MULTILINE))
        provided.update(re.findall(r"'(SCENARA_[A-Z0-9_]+)=", body))
    return provided


def test_compose_declares_required_variables() -> None:
    assert "SCENARA_OCR_ENGINE_FACTORY" in required_compose_variables()


def test_every_compose_job_provides_all_required_variables() -> None:
    required = required_compose_variables()
    jobs = compose_jobs()
    assert jobs, "no CI job uses deploy/compose.yml"
    for name, job in jobs.items():
        missing = sorted(required - provided_variables(job))
        assert not missing, f"CI job {name} does not provide: {', '.join(missing)}"


def test_ci_actions_use_node24_compatible_releases() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for action, minimum_major in NODE24_ACTION_MAJORS.items():
        versions = [int(value) for value in re.findall(rf"{re.escape(action)}@v(\d+)", workflow)]
        assert versions, f"CI workflow does not use {action}"
        assert min(versions) >= minimum_major, f"{action} must use v{minimum_major} or newer"


def test_backup_verifier_does_not_require_an_executable_file_mode() -> None:
    invocation = 'bash "$(dirname "$0")/verify-backup.sh" "$backup_dir"'
    assert invocation in BACKUP_SCRIPT.read_text(encoding="utf-8")
    assert invocation in RESTORE_SCRIPT.read_text(encoding="utf-8")
