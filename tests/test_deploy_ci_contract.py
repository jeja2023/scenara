from __future__ import annotations

import re
from pathlib import Path

import app.settings as app_settings
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "compose.yml"
ENTERPRISE_COMPOSE = ROOT / "deploy" / "compose.enterprise.yml"
DEBUG_COMPOSE = ROOT / "deploy" / "compose.debug.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
GITATTRIBUTES = ROOT / ".gitattributes"
BACKUP_SCRIPT = ROOT / "deploy" / "scripts" / "backup.sh"
RESTORE_SCRIPT = ROOT / "deploy" / "scripts" / "restore.sh"
MIGRATE_SCRIPT = ROOT / "deploy" / "scripts" / "migrate.sh"
OFFLINE_BUILD_SCRIPT = ROOT / "deploy" / "scripts" / "build-offline-bundle.sh"
OFFLINE_INSTALL_SCRIPT = ROOT / "deploy" / "scripts" / "install-offline.sh"
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
    assert {
        "SCENARA_OCR_ENGINE_FACTORY",
        "SCENARA_BEHAVIOR_ENGINE_FACTORY",
        "SCENARA_FASHION_ENGINE_FACTORY",
        "SCENARA_REDIS_PASSWORD",
        "SCENARA_MINIO_ROOT_USER",
        "SCENARA_MINIO_ROOT_PASSWORD",
        "SCENARA_ALLOWED_HOSTS",
    } <= required_compose_variables()


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
    assert 'for migration in "$SCENARA_MIGRATIONS_DIR"/*.sql' in migration
    assert "scenara_schema_migrations" in migration
    assert "migration did not atomically record its version" in migration
    assert "unsupported migration filename" in migration
    assert "http://localhost:8000/readyz" in compose


def test_debug_compose_persists_run_state_and_applies_migrations() -> None:
    document = yaml.safe_load(DEBUG_COMPOSE.read_text(encoding="utf-8"))
    services = document["services"]
    api = services["api"]
    assert api["environment"]["SCENARA_STATE_BACKEND"] == "postgres"
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert services["migrate"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["migrate"]["command"] == ["sh", "/deploy-scripts/migrate.sh"]
    assert "debug-postgres" in document["volumes"]
    assert "SCENARA_DEBUG_SECRET_ENCRYPTION_KEY" in api["environment"]
    assert api["command"] == ["sh", "deploy/scripts/debug-entrypoint.sh"]
    assert "debug-state" in document["volumes"]


def test_linux_deploy_scripts_are_forced_to_lf() -> None:
    assert "deploy/scripts/**/*.sh text eol=lf" in GITATTRIBUTES.read_text(encoding="utf-8")
    assert b"\r\n" not in MIGRATE_SCRIPT.read_bytes()


def test_production_data_service_images_are_digest_pinned() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = document["services"]
    for name in ("postgres", "migrate", "redis", "minio", "minio-init"):
        image = str(services[name]["image"])
        assert re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", image), f"{name} image is not digest-pinned"


def test_compose_hardens_runtime_and_separates_service_credentials() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    common = document["x-scenara-service"]
    assert common["user"] == "10001:10001"
    assert common["read_only"] is True
    assert common["cap_drop"] == ["ALL"]
    assert common["security_opt"] == ["no-new-privileges:true"]
    assert set(common["networks"]) == {"backend", "egress"}
    assert document["networks"]["backend"]["internal"] is True

    services = document["services"]
    assert services["redis"]["environment"]["REDISCLI_AUTH"].startswith("${SCENARA_REDIS_PASSWORD:")
    assert "--requirepass" in services["redis"]["command"]
    assert services["minio"]["environment"]["MINIO_ROOT_USER"].startswith("${SCENARA_MINIO_ROOT_USER:")
    init_env = services["minio-init"]["environment"]
    assert init_env["ROOT_USER"].startswith("${SCENARA_MINIO_ROOT_USER:")
    assert init_env["ACCESS_KEY"].startswith("${SCENARA_S3_ACCESS_KEY:")
    init_command = services["minio-init"]["command"][0]
    assert "printf '%s'" in init_command
    assert "arn:aws:s3:::$${BUCKET}" in init_command
    assert "arn:aws:s3:::$${BUCKET}/*" in init_command
    assert services["api"]["depends_on"]["preflight"]["condition"] == "service_completed_successfully"
    assert services["api"]["ports"] == ["${SCENARA_BIND_ADDRESS:-127.0.0.1}:${SCENARA_HTTP_PORT:-8000}:8000"]


def test_legacy_inference_settings_do_not_define_authentication() -> None:
    settings_source = (ROOT / "app/settings.py").read_text(encoding="utf-8")
    for name in ("LOCAL_AUTH_", "OIDC_", "JWT_", "RBAC_ENABLED", "AUTH_REQUIRED"):
        assert name not in settings_source


def test_kubernetes_foundation_has_security_gpu_migration_and_network_controls() -> None:
    kustomization = yaml.safe_load((ROOT / "deploy/kubernetes/kustomization.yaml").read_text(encoding="utf-8"))
    assert {"scheduler.yaml", "networkpolicy.yaml"} <= set(kustomization["resources"])
    assert "migrate-job.yaml" not in kustomization["resources"]
    migration_job = yaml.safe_load((ROOT / "deploy/kubernetes/migrate-job.yaml").read_text(encoding="utf-8"))
    assert migration_job["kind"] == "Job"
    api = list(yaml.safe_load_all((ROOT / "deploy/kubernetes/api.yaml").read_text(encoding="utf-8")))[0]
    pod = api["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    container = pod["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    workers = list(yaml.safe_load_all((ROOT / "deploy/kubernetes/workers.yaml").read_text(encoding="utf-8")))
    for worker in workers:
        resources = worker["spec"]["template"]["spec"]["containers"][0]["resources"]
        assert resources["requests"]["nvidia.com/gpu"] == "1"
        assert resources["limits"]["nvidia.com/gpu"] == "1"


def test_reverse_proxy_example_enforces_tls_and_preserves_streaming() -> None:
    config = (ROOT / "deploy/reverse-proxy/nginx.conf.example").read_text(encoding="utf-8")
    assert "ssl_protocols TLSv1.2 TLSv1.3" in config
    assert "server_tokens off" in config
    assert "proxy_set_header X-Forwarded-For $remote_addr" in config
    assert "proxy_request_buffering off" in config
    assert "proxy_buffering off" in config
    assert "client_max_body_size 512m" in config
    assert "return 308 https://$host$request_uri" in config


def test_gpu_workers_reserve_one_gpu_and_use_independent_device_settings() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    expected_environment = {
        "batch-worker": "${SCENARA_BATCH_GPU_DEVICE_IDS:-}",
        "stream-worker": "${SCENARA_STREAM_GPU_DEVICE_IDS:-}",
    }
    for service_name, gpu_device_ids in expected_environment.items():
        reservation = document["services"][service_name]["deploy"]["resources"]["reservations"]
        devices = reservation["devices"]
        assert devices == [{"driver": "nvidia", "count": 1, "capabilities": ["gpu"]}]
        assert document["services"][service_name]["environment"]["GPU_DEVICE_IDS"] == gpu_device_ids


def test_legacy_inference_discovers_visible_gpu_count_without_hardcoding_one(monkeypatch) -> None:
    monkeypatch.setenv("GPU_DEVICE_IDS", "2,4")
    assert app_settings._default_gpu_device_ids() == [2, 4]
    monkeypatch.delenv("GPU_DEVICE_IDS")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,4")
    assert app_settings._default_gpu_device_ids() == [0, 1]


def test_default_compose_is_personal_mode_without_enterprise_secrets() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert "secrets" not in document
    environment = document["x-scenara-environment"]
    assert environment["SCENARA_ENTERPRISE_POLICY_REQUIRED"] == "${SCENARA_ENTERPRISE_POLICY_REQUIRED:-false}"
    assert environment["GPU_DEVICE_IDS"] == "${GPU_DEVICE_IDS:-}"
    assert environment["SCENARA_POSTGRES_POOL_MIN_SIZE"] == "${SCENARA_POSTGRES_POOL_MIN_SIZE:-1}"
    assert environment["SCENARA_POSTGRES_POOL_MAX_SIZE"] == "${SCENARA_POSTGRES_POOL_MAX_SIZE:-4}"
    assert environment["SCENARA_MAX_MULTIPART_UPLOAD_BYTES"] == "${SCENARA_MAX_MULTIPART_UPLOAD_BYTES:-536870912}"
    assert "SCENARA_ENTERPRISE_LICENSE_PATH" not in environment
    assert "SCENARA_ENTERPRISE_PUBLIC_KEY_PATH" not in environment
    for service in ("api", "batch-worker", "stream-worker", "scheduler"):
        assert "secrets" not in document["services"][service]


def test_enterprise_compose_is_an_explicit_signed_license_extension() -> None:
    document = yaml.safe_load(ENTERPRISE_COMPOSE.read_text(encoding="utf-8"))
    assert set(document["services"]) == {"api", "batch-worker", "stream-worker", "scheduler"}
    for service in document["services"].values():
        environment = service["environment"]
        assert environment["SCENARA_ENTERPRISE_POLICY_REQUIRED"] == "true"
        assert environment["SCENARA_ENTERPRISE_LICENSE_PATH"] == "/run/secrets/scenara_enterprise_license"
        assert environment["SCENARA_ENTERPRISE_PUBLIC_KEY_PATH"] == "/run/secrets/scenara_enterprise_public_key"
        assert service["secrets"] == ["scenara_enterprise_license", "scenara_enterprise_public_key"]
    assert ":?set SCENARA_ENTERPRISE_LICENSE_FILE" in document["secrets"]["scenara_enterprise_license"]["file"]
    assert ":?set SCENARA_ENTERPRISE_PUBLIC_KEY_FILE" in document["secrets"]["scenara_enterprise_public_key"]["file"]


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
    assert 'cp "$repo_root/deploy/compose.enterprise.yml" "$staging/deploy/compose.enterprise.yml"' in offline_build


def test_docker_build_copies_manifests_before_installing_dependencies() -> None:
    dockerfile_lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    manifest_copy = dockerfile_lines.index(
        "COPY frontend/console/package.json frontend/console/package.json"
    )
    dependency_install = dockerfile_lines.index("RUN pnpm install --frozen-lockfile")
    assert manifest_copy < dependency_install
    source_copy = dockerfile_lines.index("COPY frontend/console frontend/console")
    assert dependency_install < source_copy
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "postgresql-client" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    dockerfile_data = (ROOT / "Dockerfile.data").read_text(encoding="utf-8")
    assert re.search(r"^FROM node:[^\s]+@sha256:[0-9a-f]{64}", dockerfile, re.MULTILINE)
    assert re.search(r"^FROM nvidia/cuda:[^\s]+@sha256:[0-9a-f]{64}", dockerfile, re.MULTILINE)
    assert re.search(r"^FROM python:[^\s]+@sha256:[0-9a-f]{64}", dockerfile_data, re.MULTILINE)


def test_default_runtime_model_references_use_cache_key_contract() -> None:
    models_document = yaml.safe_load(MODEL_CONFIG.read_text(encoding="utf-8"))
    capabilities_document = yaml.safe_load(MODEL_CAPABILITIES.read_text(encoding="utf-8"))
    models = models_document["models"]
    aliases = models_document["aliases"]
    assert set(models) == {
        "scenara.portrait/yolov8n",
        "scenara.portrait/osnet_ibn_x1_0",
        "scenara.portrait/scrfd_10g",
        "scenara.portrait/arcface_r100",
        "scenara.portrait/attribute_reid",
        "scenara.portrait/opengait_gait3d",
    }
    assert aliases["person_detector_default"]["target"] in models
    assert aliases["person_reid_default"]["target"] in models
    assert capabilities_document["capabilities"]["person_detection"]["model_id"] == "person_detector_default"
    assert capabilities_document["capabilities"]["body_embedding"]["model_id"] == "person_reid_default"


def test_integration_service_bootstrap_is_split_and_retried() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["integration-services"]["steps"]
    named_steps = {step.get("name"): step for step in steps if step.get("name")}
    expected_commands = {
        "Start PostgreSQL, Redis, and MinIO": "up -d --wait postgres redis minio",
        "Apply integration database migrations": "run --rm migrate",
        "Initialize integration object store": "run --rm minio-init",
    }
    for name, command in expected_commands.items():
        script = named_steps[name]["run"]
        assert "for attempt in 1 2 3" in script
        assert command in script
        assert 'if [ "$attempt" -eq 3 ]; then exit 1; fi' in script


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


def test_offline_installer_records_gpu_memory_without_a_fixed_capacity_gate() -> None:
    installer = OFFLINE_INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "gpu_memory_mib=%s" in installer
    assert '"schema_version": "1.0"' in installer
    assert '"evidence_type": "offline_install"' in installer
    assert 'refusing to overwrite existing result' in installer
    assert "23000" not in installer
    assert "24 GB" not in installer
    assert "requires exactly one NVIDIA GPU" not in installer
    assert 'gpu_count=%s' in installer
    assert "check.example_clients=passed" not in installer
    assert "check.core_parse=passed" not in installer


def test_ci_checks_legacy_adapter_code_and_enforces_coverage() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    package = (ROOT / "package.json").read_text(encoding="utf-8")
    console_package = (ROOT / "frontend" / "console" / "package.json").read_text(encoding="utf-8")
    assert "ruff check scenara app tests sdk/python scripts" in workflow
    assert "mypy scenara app sdk/python/scenara_sdk" in workflow
    assert "--cov=app" in workflow
    assert "--cov-fail-under=60" in workflow
    assert '"console:format:check"' in package
    assert '"format:check"' in console_package
