from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_IMPLEMENTATION = (
    "scenara/domains/portrait/analysis.py",
    "scenara/domains/portrait/service.py",
    "scenara/domains/ocr/operators.py",
    "scenara/enterprise/license.py",
    "scenara/enterprise/service.py",
    "scenara/platform/media_batch.py",
    "scenara/platform/features.py",
    "scenara/infrastructure/qdrant_features.py",
    "scenara/infrastructure/triton_model.py",
    "scenara/infrastructure/mlflow_tracking.py",
    "scenara_data/app.py",
    "scenara_data/__main__.py",
    "scenara/platform/feedback.py",
    "scenara/infrastructure/postgres_feedback.py",
    "scenara/platform/control_plane.py",
    "scenara/platform/control_plane_store.py",
    "scenara/api/routers/audit.py",
    "scenara/api/routers/catalog.py",
    "scenara/api/routers/surveillance.py",
    "scenara/api/routers/access.py",
    "scenara/api/routers/datasets.py",
    "scenara/api/routers/media.py",
    "scenara/api/routers/runs.py",
    "scenara/api/routers/parse.py",
    "scenara/api/routers/portrait.py",
    "scenara/api/routers/search.py",
    "scenara/api/routers/enterprise.py",
    "scenara/api/routers/feedback.py",
    "scenara/api/routers/iam.py",
    "scenara/api/routers/data_governance.py",
    "scenara/api/routers/flows.py",
    "scenara/api/routers/portrait_intelligence.py",
    "scenara/api/routers/edge.py",
    "scenara/api/routers/agents.py",
    "scenara/api/routers/operations.py",
    "scenara/infrastructure/postgres_control_plane.py",
    "migrations/0009_control_plane_records.sql",
    "migrations/0010_user_credentials.sql",
    "migrations/0011_session_token_index.sql",
    "frontend/console/src/views/ResultsView.vue",
    "frontend/console/src/composables/useDomainCatalog.ts",
    "frontend/console/src/composables/useMediaPreview.ts",
    "frontend/console/src/composables/useDebouncedRef.ts",
    "frontend/console/src/views/access/types.ts",
    "frontend/console/src/views/access/config.ts",
    "frontend/console/src/views/access/FoundationTab.vue",
    "frontend/console/src/views/access/ConnectionTab.vue",
    "frontend/console/src/views/access/ProductsTab.vue",
    "frontend/console/src/views/access/EventsTab.vue",
    "frontend/console/src/views/access/CredentialsTab.vue",
    "frontend/console/src/views/access/IdentityTab.vue",
    "frontend/console/src/views/access/IdentityDialogs.vue",
    "frontend/console/src/views/access/CredentialsDialogs.vue",
    "frontend/console/src/views/access/ProductsDialog.vue",
    "frontend/console/src/views/access/EventsDialog.vue",
    "frontend/console/src/views/access/IssuedKeyDialog.vue",
    "frontend/console/src/views/FeedbackView.vue",
    "frontend/console/src/views/feedback/feedback-workbench.css",
    "frontend/console/src/views/parse/ParseHistoryPanel.vue",
    "frontend/console/src/views/parse/ParseInputControls.vue",
    "frontend/console/src/views/parse/ParseMediaPreview.vue",
    "frontend/console/src/views/parse/ParseWorkspaceToolbar.vue",
    "frontend/console/src/views/parse/parse-workbench.css",
    "frontend/console/src/views/parse/useParseMediaInput.ts",
    "frontend/console/src/views/parse/useParseParameters.ts",
    "frontend/console/src/views/parse/useRoiSelection.ts",
    "frontend/console/src/views/parse/useResultPreview.ts",
    "frontend/console/src/views/parse/useRunTracker.ts",
    "sdk/python/scenara_sdk/client.py",
    "sdk/typescript/src/generated.ts",
    "deploy/compose.yml",
    "deploy/compose.data.yml",
    "Dockerfile.data",
    "deploy/compose.enterprise.yml",
    "deploy/OPERATIONS.md",
    "deploy/PRODUCTION_CHECKLIST.md",
    "deploy/reverse-proxy/nginx.conf.example",
    "deploy/kubernetes/ingress.example.yaml",
    "deploy/scripts/build-offline-bundle.sh",
    "deploy/scripts/install-offline.sh",
    "deploy/scripts/migrate.sh",
    "deploy/scripts/backup.sh",
    "deploy/scripts/restore.sh",
    "scripts/prepare_runtime_state.py",
    "scripts/generate_production_env.py",
    "scripts/validate_production_config.py",
    "scripts/prepare_release_evidence.py",
    "scripts/record_release_evidence.py",
    "scripts/rebuild_redis_queue.py",
    "docs/OBJECT_STORAGE_PROVIDERS.md",
    "tests/object_store_contract.py",
    "tests/test_object_store.py",
    "requirements/production.lock",
    "frontend/console/playwright.config.ts",
    "frontend/console/e2e/workspaces.spec.ts",
    "tests/test_control_plane.py",
    "docs/release/0.3.0-dev.30.md",
    "docs/release/0.3.0-dev.31.md",
    "docs/release/0.3.0-dev.32.md",
    "docs/release/0.3.0-dev.33.md",
    "docs/release/0.3.0-dev.34.md",
    "docs/release/0.3.0-dev.39.md",
    "docs/release/0.3.0-dev.40.md",
    "docs/release/SUPPORT_MATRIX.md",
    "docs/release/EVIDENCE_OWNERS.md",
    "docs/release/evidence/QUALIFICATION_INPUTS.md",
    "docs/release/evidence/manifest.example.json",
)
REQUIRED_EVIDENCE_TYPES = {
    "backup_restore",
    "gpu_capacity",
    "integration_services",
    "model_rights",
    "behavior_evaluation",
    "fashion_evaluation",
    "ocr_evaluation",
    "offline_install",
    "portrait_evaluation",
    "security_assessment",
    "software_license",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
RELEASE_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
PLACEHOLDER = re.compile(r"(?:<[^>]+>|\b(?:example|replace|todo|tbd)\b|待填写|占位)", re.IGNORECASE)
LICENSE_PLACEHOLDER = re.compile(r"engineering placeholder|must receive legal review", re.IGNORECASE)
RELEASE_IDENTITY_FIELDS = {
    "source_commit",
    "image_digest",
    "offline_bundle_sha256",
    "openapi_sha256",
    "model_set_sha256",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def implementation_errors() -> list[str]:
    errors = [
        f"missing implementation deliverable: {name}" for name in REQUIRED_IMPLEMENTATION if not (ROOT / name).is_file()
    ]
    openapi = ROOT / "docs/openapi.json"
    generated = ROOT / "sdk/typescript/src/generated.ts"
    if openapi.is_file() and generated.is_file():
        try:
            generator = importlib.import_module("scripts.generate_typescript_sdk")
        except ModuleNotFoundError:
            generator = importlib.import_module("generate_typescript_sdk")
        render_typescript_sdk = generator.render

        document = json.loads(openapi.read_text(encoding="utf-8"))
        if generated.read_text(encoding="utf-8") != render_typescript_sdk(document):
            errors.append("generated TypeScript schemas do not match docs/openapi.json")
    return errors


def repository_commit(root: Path = ROOT) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def license_errors(root: Path = ROOT) -> list[str]:
    path = root / "LICENSE"
    if not path.is_file():
        return ["software license is missing"]
    if LICENSE_PLACEHOLDER.search(path.read_text(encoding="utf-8", errors="ignore")):
        return ["software license still contains the engineering legal-review placeholder"]
    return []


def _timestamp(raw: Any, name: str, evidence_type: str, errors: list[str]) -> datetime | None:
    if not isinstance(raw, str):
        errors.append(f"{evidence_type}: {name} must be an ISO-8601 string")
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{evidence_type}: {name} must be valid ISO-8601")
        return None


def _string_set(metadata: dict[str, Any], field: str, evidence_type: str, errors: list[str]) -> set[str]:
    value = metadata.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{evidence_type}: metadata.{field} must be a list of non-empty strings")
        return set()
    return set(value)


def _required_values(metadata: dict[str, Any], names: set[str], evidence_type: str) -> list[str]:
    return [f"{evidence_type}: metadata.{name} is required" for name in sorted(names) if metadata.get(name) is None]


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metadata_errors(evidence_type: str, metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if evidence_type in {"portrait_evaluation", "ocr_evaluation", "behavior_evaluation", "fashion_evaluation"}:
        if not metadata.get("dataset_version") or metadata.get("rights_cleared") is not True:
            errors.append(f"{evidence_type}: versioned and rights-cleared dataset evidence is required")
        if not _valid_sha256(metadata.get("dataset_manifest_sha256")):
            errors.append(f"{evidence_type}: dataset_manifest_sha256 must be a SHA-256")
        if not isinstance(metadata.get("metrics"), dict) or not metadata["metrics"]:
            errors.append(f"{evidence_type}: fixed evaluation metrics are required")
        if not isinstance(metadata.get("thresholds"), dict) or not metadata["thresholds"]:
            errors.append(f"{evidence_type}: fixed evaluation thresholds are required")
        if not isinstance(metadata.get("tolerances"), dict) or not metadata["tolerances"]:
            errors.append(f"{evidence_type}: fixed evaluation tolerances are required")
        if not _valid_sha256(metadata.get("thresholds_sha256")):
            errors.append(f"{evidence_type}: thresholds_sha256 must be a SHA-256")
        fixed_at = _timestamp(
            metadata.get("thresholds_fixed_at"),
            "metadata.thresholds_fixed_at",
            evidence_type,
            errors,
        )
        if fixed_at is not None and fixed_at.utcoffset() is None:
            errors.append(f"{evidence_type}: thresholds_fixed_at must include a timezone")
        if metadata.get("thresholds_fixed_before_run") is not True:
            errors.append(f"{evidence_type}: thresholds must be fixed before evaluation")
        runs = metadata.get("runs")
        if not isinstance(runs, list) or len(runs) < 2:
            errors.append(f"{evidence_type}: metadata.runs must contain at least two run records")
            runs = []
        run_ids: set[str] = set()
        for index, run in enumerate(runs):
            if not isinstance(run, dict):
                errors.append(f"{evidence_type}: metadata.runs[{index}] must be an object")
                continue
            run_id = run.get("run_id")
            if not isinstance(run_id, str) or not run_id or PLACEHOLDER.search(run_id):
                errors.append(f"{evidence_type}: metadata.runs[{index}].run_id is required")
            elif run_id in run_ids:
                errors.append(f"{evidence_type}: independent run ids must be unique")
            else:
                run_ids.add(run_id)
            if not _valid_sha256(run.get("output_sha256")):
                errors.append(f"{evidence_type}: metadata.runs[{index}].output_sha256 must be a SHA-256")
            if run.get("exit_code") != 0:
                errors.append(f"{evidence_type}: metadata.runs[{index}].exit_code must be zero")
            run_at = _timestamp(
                run.get("executed_at"),
                f"metadata.runs[{index}].executed_at",
                evidence_type,
                errors,
            )
            if run_at is not None and run_at.utcoffset() is None:
                errors.append(
                    f"{evidence_type}: metadata.runs[{index}].executed_at must include a timezone"
                )
            if (
                fixed_at is not None
                and fixed_at.utcoffset() is not None
                and run_at is not None
                and run_at.utcoffset() is not None
                and run_at <= fixed_at
            ):
                errors.append(f"{evidence_type}: thresholds must be fixed before every run")
            if not isinstance(run.get("metrics"), dict) or not run["metrics"]:
                errors.append(f"{evidence_type}: metadata.runs[{index}].metrics are required")
        if metadata.get("independent_runs") != len(runs) or len(runs) < 2:
            errors.append(f"{evidence_type}: independent_runs must match metadata.runs")
        thresholds = metadata.get("thresholds")
        tolerances = metadata.get("tolerances")
        checked_metrics: set[str] = set()
        if isinstance(thresholds, dict) and isinstance(tolerances, dict):
            for threshold_name, threshold_value in thresholds.items():
                if threshold_name.endswith("_min"):
                    metric_name = threshold_name[:-4]
                    minimum = True
                elif threshold_name.endswith("_max"):
                    metric_name = threshold_name[:-4]
                    minimum = False
                else:
                    errors.append(
                        f"{evidence_type}: threshold {threshold_name} must end in _min or _max"
                    )
                    continue
                limit = _finite_number(threshold_value)
                if limit is None:
                    errors.append(f"{evidence_type}: threshold {threshold_name} must be finite")
                    continue
                checked_metrics.add(metric_name)
                for index, run in enumerate(runs):
                    if not isinstance(run, dict):
                        continue
                    measured = _finite_number(
                        run.get("metrics", {}).get(metric_name)
                        if isinstance(run.get("metrics"), dict)
                        else None
                    )
                    if measured is None:
                        errors.append(
                            f"{evidence_type}: metadata.runs[{index}].metrics.{metric_name} must be finite"
                        )
                    elif (minimum and measured < limit) or (not minimum and measured > limit):
                        errors.append(
                            f"{evidence_type}: metadata.runs[{index}].metrics.{metric_name} fails {threshold_name}"
                        )
            if set(tolerances) != checked_metrics:
                errors.append(
                    f"{evidence_type}: tolerances must cover exactly the threshold metrics"
                )
            for metric_name, tolerance_value in tolerances.items():
                tolerance = _finite_number(tolerance_value)
                values = [
                    _finite_number(run.get("metrics", {}).get(metric_name))
                    for run in runs
                    if isinstance(run, dict) and isinstance(run.get("metrics"), dict)
                ]
                if tolerance is None or tolerance < 0:
                    errors.append(
                        f"{evidence_type}: tolerance {metric_name} must be finite and non-negative"
                    )
                elif len(values) == len(runs) and all(value is not None for value in values):
                    finite_values = [value for value in values if value is not None]
                    if max(finite_values) - min(finite_values) > tolerance:
                        errors.append(
                            f"{evidence_type}: independent runs exceed tolerance for {metric_name}"
                        )
        if metadata.get("within_tolerance") is not True:
            errors.append(f"{evidence_type}: two reproducible runs within the fixed tolerance are required")
        command = metadata.get("command")
        if not isinstance(command, str) or not command or PLACEHOLDER.search(command):
            errors.append(f"{evidence_type}: reproducible evaluation command is required")
    elif evidence_type == "gpu_capacity":
        # Capacity qualification records the observed device.  Memory size is
        # intentionally descriptive; qualification is decided by the measured
        # workload and scenario outcomes below, not by a fixed 24 GB gate.
        gpu_memory = _finite_number(metadata.get("gpu_memory_mib"))
        if gpu_memory is None or gpu_memory <= 0:
            errors.append("gpu_capacity: gpu_memory_mib must be positive")
        required = {"sustained_load", "burst", "vram_pressure", "backpressure", "recovery"}
        if not required <= _string_set(metadata, "scenarios", evidence_type, errors):
            errors.append("gpu_capacity: all capacity and recovery scenarios are required")
        errors.extend(
            _required_values(
                metadata,
                {"p50_ms", "p95_ms", "p99_ms", "throughput_per_second", "error_rate", "peak_vram_mib"},
                evidence_type,
            )
        )
        for field in ("gpu_name", "driver_version", "command"):
            value = metadata.get(field)
            if not isinstance(value, str) or not value or PLACEHOLDER.search(value):
                errors.append(f"gpu_capacity: metadata.{field} is required")
        if not _valid_sha256(metadata.get("raw_result_sha256")):
            errors.append("gpu_capacity: raw_result_sha256 must be a SHA-256")
        duration = _finite_number(metadata.get("duration_seconds"))
        if duration is None or duration <= 0:
            errors.append("gpu_capacity: duration_seconds must be positive")
        p50 = _finite_number(metadata.get("p50_ms"))
        p95 = _finite_number(metadata.get("p95_ms"))
        p99 = _finite_number(metadata.get("p99_ms"))
        if p50 is None or p95 is None or p99 is None or not 0 <= p50 <= p95 <= p99:
            errors.append("gpu_capacity: latency percentiles must satisfy 0 <= p50 <= p95 <= p99")
        throughput = _finite_number(metadata.get("throughput_per_second"))
        if throughput is None or throughput <= 0:
            errors.append("gpu_capacity: throughput_per_second must be positive")
        error_rate = _finite_number(metadata.get("error_rate"))
        if error_rate is None or not 0 <= error_rate <= 1:
            errors.append("gpu_capacity: error_rate must be between 0 and 1")
        peak_vram = _finite_number(metadata.get("peak_vram_mib"))
        if peak_vram is None or gpu_memory is None or not 0 <= peak_vram <= gpu_memory:
            errors.append("gpu_capacity: peak_vram_mib must fit the target GPU")
        scenario_results = metadata.get("scenario_results")
        if not isinstance(scenario_results, dict):
            errors.append("gpu_capacity: scenario_results must be an object")
            scenario_results = {}
        for scenario in sorted(required):
            result = scenario_results.get(scenario)
            if not isinstance(result, dict) or result.get("status") != "passed":
                errors.append(f"gpu_capacity: scenario_results.{scenario}.status must be passed")
                continue
            if result.get("exit_code") != 0:
                errors.append(f"gpu_capacity: scenario_results.{scenario}.exit_code must be zero")
            if not _valid_sha256(result.get("output_sha256")):
                errors.append(
                    f"gpu_capacity: scenario_results.{scenario}.output_sha256 must be a SHA-256"
                )
    elif evidence_type == "integration_services":
        required = {"postgres_pgvector", "redis", "minio"}
        if not required <= _string_set(metadata, "services", evidence_type, errors):
            errors.append("integration_services: PostgreSQL/pgvector, Redis, and MinIO are required")
        if metadata.get("skipped_tests") != 0 or metadata.get("duplicate_logical_results") != 0:
            errors.append("integration_services: no skipped tests or duplicate logical results are allowed")
        if metadata.get("redis_rebuild_verified") is not True:
            errors.append("integration_services: Redis rebuild from PostgreSQL and MinIO must be verified")
    elif evidence_type == "security_assessment":
        required = {
            "audit_fail_closed",
            "authorization",
            "biometric_deletion",
            "credential_redaction",
            "malicious_media",
            "ssrf",
        }
        if not required <= _string_set(metadata, "scenarios", evidence_type, errors):
            errors.append("security_assessment: all required security scenarios must be covered")
    elif evidence_type == "model_rights":
        models = metadata.get("models")
        if not isinstance(models, list) or not models:
            errors.append("model_rights: metadata.models must be a non-empty list of model records")
            models = []
        required_fields = {
            "artifact_sha256",
            "license_identifier",
            "license_source_uri",
            "model_id",
            "model_version",
            "rights_record_sha256",
            "source_uri",
        }
        model_keys: set[tuple[str, str]] = set()
        for index, model in enumerate(models):
            if not isinstance(model, dict):
                errors.append(f"model_rights: metadata.models[{index}] must be an object")
                continue
            missing = sorted(
                field
                for field in required_fields
                if not isinstance(model.get(field), str)
                or not model[field]
                or PLACEHOLDER.search(model[field])
            )
            if missing:
                errors.append(
                    f"model_rights: metadata.models[{index}] is missing objective fields: "
                    + ", ".join(missing)
                )
            if not SHA256.fullmatch(str(model.get("artifact_sha256", ""))):
                errors.append(f"model_rights: metadata.models[{index}].artifact_sha256 must be a SHA-256")
            if not _valid_sha256(model.get("rights_record_sha256")):
                errors.append(f"model_rights: metadata.models[{index}].rights_record_sha256 must be a SHA-256")
            key = (str(model.get("model_id", "")), str(model.get("model_version", "")))
            if key in model_keys:
                errors.append("model_rights: model id and version records must be unique")
            model_keys.add(key)
            for field in (
                "intended_use_allowed",
                "redistribution_allowed",
                "rights_cleared",
                "source_identity_verified",
            ):
                if model.get(field) is not True:
                    errors.append(f"model_rights: metadata.models[{index}].{field} must be true")
        if metadata.get("all_rights_cleared") is not True or not models:
            errors.append("model_rights: every production model must have cleared rights")
    elif evidence_type == "software_license":
        errors.extend(
            _required_values(
                metadata,
                {"license_sha256", "license_identifier", "review_basis"},
                evidence_type,
            )
        )
        required = {
            "compliance",
            "copyright_and_ownership",
            "grant_and_restrictions",
            "termination",
            "third_party_materials",
            "warranty_and_liability",
        }
        if metadata.get("review_basis") != "personal_project_self_review":
            errors.append("software_license: review_basis must identify the personal-project self-review")
        if not required <= _string_set(metadata, "review_scope", evidence_type, errors):
            errors.append("software_license: all license self-review areas are required")
    elif evidence_type == "offline_install":
        required = {"health", "console", "example_clients", "core_parse"}
        if metadata.get("blank_host") is not True or metadata.get("isolated_network") is not True:
            errors.append("offline_install: a blank isolated target host is required")
        checks = _string_set(metadata, "checks", evidence_type, errors)
        if metadata.get("checksums_verified") is not True or not required <= checks:
            errors.append("offline_install: checksums and all smoke checks must pass")
        if metadata.get("host_os") != "ubuntu" or metadata.get("host_version") != "24.04":
            errors.append("offline_install: target host must be Ubuntu 24.04")
        gpu_memory = _finite_number(metadata.get("gpu_memory_mib"))
        if gpu_memory is None or gpu_memory <= 0:
            errors.append("offline_install: gpu_memory_mib must be positive")
        for field in ("bundle_sha256", "installer_output_sha256"):
            if not _valid_sha256(metadata.get(field)):
                errors.append(f"offline_install: {field} must be a SHA-256")
        if metadata.get("installer_exit_code") != 0:
            errors.append("offline_install: installer_exit_code must be zero")
        if not SOURCE_COMMIT.fullmatch(str(metadata.get("source_commit", ""))):
            errors.append("offline_install: source_commit must be a full lowercase Git SHA")
        services = metadata.get("services")
        required_services = {"api", "batch-worker", "stream-worker", "scheduler", "postgres", "redis", "minio"}
        if not isinstance(services, dict) or any(services.get(name) != "running" for name in required_services):
            errors.append("offline_install: every required service must be running")
        check_results = metadata.get("check_results")
        if not isinstance(check_results, dict):
            errors.append("offline_install: check_results must be an object")
            check_results = {}
        for check in sorted(required):
            result = check_results.get(check)
            if not isinstance(result, dict) or result.get("status") != "passed":
                errors.append(f"offline_install: check_results.{check}.status must be passed")
                continue
            if result.get("exit_code") != 0:
                errors.append(f"offline_install: check_results.{check}.exit_code must be zero")
            if not _valid_sha256(result.get("output_sha256")):
                errors.append(
                    f"offline_install: check_results.{check}.output_sha256 must be a SHA-256"
                )
    elif evidence_type == "backup_restore":
        required = {"tenants", "projects", "media", "runs", "results", "pipelines", "models", "audit", "biometrics"}
        if (
            _number(metadata.get("rpo_hours"), float("inf")) > 24
            or _number(metadata.get("rto_hours"), float("inf")) > 4
        ):
            errors.append("backup_restore: RPO must be <=24h and RTO must be <=4h")
        if not required <= _string_set(metadata, "entities_verified", evidence_type, errors):
            errors.append("backup_restore: all required business entities must be verified")
    return errors


def validate_entry(
    entry: Any,
    *,
    release_identity: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> list[str]:
    if not isinstance(entry, dict):
        return ["evidence manifest entry must be an object"]
    evidence_type = str(entry.get("evidence_type", ""))
    errors: list[str] = []
    status = entry.get("status")
    if status not in {"pending", "passed"}:
        errors.append(f"{evidence_type}: status must be pending or passed")
    report_value = entry.get("report")
    report = (root / str(report_value)).resolve() if report_value else None
    reports_root = (root / "docs/release/evidence/reports").resolve()
    if evidence_type not in REQUIRED_EVIDENCE_TYPES:
        errors.append(f"unknown evidence type: {evidence_type or '<missing>'}")
    if report is not None and reports_root not in report.parents:
        errors.append(f"{evidence_type}: report must be inside docs/release/evidence/reports")
    if status == "pending":
        if report_value is not None or entry.get("sha256") is not None or entry.get("executed_at") is not None:
            errors.append(f"{evidence_type}: pending evidence must not claim a report, digest, or execution time")
        if entry.get("metadata") not in ({}, None):
            errors.append(f"{evidence_type}: pending evidence metadata must be empty")
        return errors
    if report is None or not report.is_file():
        errors.append(f"{evidence_type}: report file is missing")
    else:
        if not SHA256.fullmatch(str(entry.get("sha256", ""))) or digest(report) != entry.get("sha256"):
            errors.append(f"{evidence_type}: report SHA-256 does not match")
        try:
            report_document = json.loads(report.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            errors.append(f"{evidence_type}: report must be UTF-8 JSON")
        else:
            expected = {
                key: entry.get(key)
                for key in (
                    "evidence_type",
                    "status",
                    "executed_at",
                    "target",
                    "release_identity",
                    "metadata",
                )
            }
            actual = {key: report_document.get(key) for key in expected} if isinstance(report_document, dict) else {}
            if not isinstance(report_document, dict) or report_document.get("schema_version") != "1.0":
                errors.append(f"{evidence_type}: report schema_version must be 1.0")
            if actual != expected:
                errors.append(f"{evidence_type}: report content does not match the manifest entry")
    _timestamp(entry.get("executed_at"), "executed_at", evidence_type, errors)
    target = entry.get("target")
    if not isinstance(target, str) or not target or PLACEHOLDER.search(target):
        errors.append(f"{evidence_type}: target must be a non-placeholder value")
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"{evidence_type}: metadata must be an object")
        metadata = {}
    errors.extend(_metadata_errors(evidence_type, metadata))
    if release_identity is not None and entry.get("release_identity") != release_identity:
        errors.append(f"{evidence_type}: release identity does not match the manifest")
    if evidence_type == "software_license":
        license_path = root / "LICENSE"
        if license_path.is_file() and metadata.get("license_sha256") != digest(license_path):
            errors.append("software_license: LICENSE SHA-256 does not match")
    return errors


def evidence_errors(
    manifest_path: Path,
    *,
    root: Path = ROOT,
    expected_source_commit: str | None = None,
) -> list[str]:
    if not manifest_path.is_file():
        return [f"release evidence manifest is missing: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ["release evidence manifest must be UTF-8 JSON"]
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        return ["release evidence manifest entries must be a list"]
    errors: list[str] = []
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.2":
        errors.append("release evidence manifest schema_version must be 1.2")
    if not isinstance(manifest, dict) or not RELEASE_VERSION.fullmatch(str(manifest.get("release", ""))):
        errors.append("release evidence manifest release must be a semantic version")
    release_identity_value = manifest.get("release_identity") if isinstance(manifest, dict) else None
    release_identity: dict[str, Any] | None = None
    if not isinstance(release_identity_value, dict):
        errors.append("release evidence manifest release_identity must be an object")
    else:
        release_identity = {key: release_identity_value.get(key) for key in RELEASE_IDENTITY_FIELDS}
        if set(release_identity_value) != RELEASE_IDENTITY_FIELDS:
            errors.append("release identity must contain exactly the required artifact fields")
        source_commit = release_identity["source_commit"]
        if source_commit is not None and (
            not isinstance(source_commit, str) or not SOURCE_COMMIT.fullmatch(source_commit)
        ):
            errors.append("release identity source_commit must be null or a full lowercase Git SHA")
        image_digest = release_identity["image_digest"]
        if image_digest is not None and (
            not isinstance(image_digest, str) or not IMAGE_DIGEST.fullmatch(image_digest)
        ):
            errors.append("release identity image_digest must be null or a sha256 container digest")
        for field in ("offline_bundle_sha256", "openapi_sha256", "model_set_sha256"):
            value = release_identity[field]
            if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
                errors.append(f"release identity {field} must be null or a lowercase SHA-256")
        openapi = root / "docs/openapi.json"
        if (
            openapi.is_file()
            and release_identity["openapi_sha256"] is not None
            and release_identity["openapi_sha256"] != digest(openapi)
        ):
            errors.append("release identity openapi_sha256 does not match docs/openapi.json")
    present: set[str] = set()
    for entry in entries:
        errors.extend(validate_entry(entry, release_identity=release_identity, root=root))
        if isinstance(entry, dict):
            evidence_type = str(entry.get("evidence_type", ""))
            if evidence_type in present:
                errors.append(f"duplicate release evidence type: {evidence_type}")
            present.add(evidence_type)
    for missing in sorted(REQUIRED_EVIDENCE_TYPES - present):
        errors.append(f"missing release evidence type: {missing}")
    pending = sorted(
        str(entry.get("evidence_type"))
        for entry in entries
        if isinstance(entry, dict) and entry.get("status") == "pending"
    )
    if pending:
        errors.append(f"pending release evidence: {', '.join(pending)}")
    elif release_identity is not None:
        missing_identity = sorted(key for key, value in release_identity.items() if value is None)
        if missing_identity:
            errors.append(f"completed release identity is missing: {', '.join(missing_identity)}")
        elif expected_source_commit is not None and release_identity["source_commit"] != expected_source_commit:
            errors.append("release identity source_commit does not match the checked-out commit")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Scenara implementation and release evidence")
    parser.add_argument("--implementation-only", action="store_true")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "docs/release/evidence/manifest.json",
    )
    args = parser.parse_args()
    errors = implementation_errors()
    if not args.implementation_only:
        errors.extend(license_errors())
        errors.extend(
            evidence_errors(
                args.manifest.resolve(),
                expected_source_commit=repository_commit(),
            )
        )
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
