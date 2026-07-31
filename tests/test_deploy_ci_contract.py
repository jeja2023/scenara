from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "compose.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BACKUP_SCRIPT = ROOT / "deploy" / "scripts" / "backup.sh"
RESTORE_SCRIPT = ROOT / "deploy" / "scripts" / "restore.sh"
MIGRATE_SCRIPT = ROOT / "deploy" / "scripts" / "migrate.sh"
OFFLINE_BUILD_SCRIPT = ROOT / "deploy" / "scripts" / "build-offline-bundle.sh"
DOCKERFILE = ROOT / "Dockerfile"
MODEL_CONFIG = ROOT / "models.yml"
MODEL_CAPABILITIES = ROOT / "model-capabilities.yml"
PRODUCTION_LOCK = ROOT / "requirements" / "production.lock"
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


def test_compose_runs_all_versioned_migrations_and_checks_readiness() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    migration = MIGRATE_SCRIPT.read_text(encoding="utf-8")
    assert '["sh", "/deploy-scripts/migrate.sh"]' in compose
    assert "for migration in /migrations/*.sql" in migration
    assert "scenara_schema_migrations" in migration
    assert "migration did not atomically record its version" in migration
    assert "unsupported migration filename" in migration
    assert "http://localhost:8000/readyz" in compose


def test_production_data_service_images_are_digest_pinned() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = document["services"]
    for name in ("postgres", "migrate", "redis", "minio", "minio-init"):
        image = str(services[name]["image"])
        assert re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", image), f"{name} image is not digest-pinned"


def test_production_dependencies_are_hash_locked_everywhere() -> None:
    lock = PRODUCTION_LOCK.read_text(encoding="utf-8")
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    offline_build = OFFLINE_BUILD_SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "--hash=sha256:" in lock
    assert "--require-hashes -r requirements/production.lock" in dockerfile
    assert "--require-hashes" in offline_build
    assert '-r "$repo_root/requirements/production.lock"' in offline_build
    assert "uv pip compile requirements/production.in --python-version 3.12" in workflow
    assert "--python-platform x86_64-manylinux_2_28" in workflow
    assert "git diff --exit-code -- requirements/production.lock" in workflow


def test_docker_build_copies_workspace_sources_before_installing_dependencies() -> None:
    dockerfile_lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    source_copy = dockerfile_lines.index("COPY frontend/console frontend/console")
    dependency_install = dockerfile_lines.index("RUN pnpm install --frozen-lockfile")
    assert source_copy < dependency_install


def test_default_runtime_model_references_use_cache_key_contract() -> None:
    models_document = yaml.safe_load(MODEL_CONFIG.read_text(encoding="utf-8"))
    capabilities_document = yaml.safe_load(MODEL_CAPABILITIES.read_text(encoding="utf-8"))
    models = models_document["models"]
    aliases = models_document["aliases"]
    assert set(models) == {
        "scenara.portrait/yolov8n",
        "scenara.portrait/osnet_ibn_x1_0",
    }
    assert aliases["person_detector_default"]["target"] in models
    assert aliases["person_reid_default"]["target"] in models
    assert capabilities_document["capabilities"]["person_detection"]["model_id"] == "person_detector_default"
    assert capabilities_document["capabilities"]["body_embedding"]["model_id"] == "person_reid_default"


def test_offline_builder_emits_release_identity_and_model_manifest() -> None:
    offline_build = OFFLINE_BUILD_SCRIPT.read_text(encoding="utf-8")
    for field in (
        "source_commit",
        "image_digest",
        "offline_bundle_sha256",
        "openapi_sha256",
        "model_set_sha256",
    ):
        assert f'"{field}"' in offline_build
    assert "model-SHA256SUMS" in offline_build
    assert "container-images.txt" in offline_build
    assert "release-identity.json" in offline_build


def test_ci_checks_legacy_adapter_code_and_enforces_coverage() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "ruff check --select E4,E7,E9,F app" in workflow
    assert "mypy scenara app sdk/python/scenara_sdk" in workflow
    assert "--cov-fail-under=75" in workflow
