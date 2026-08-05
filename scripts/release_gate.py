from __future__ import annotations

import argparse
import hashlib
import importlib
import json
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
    "scenara/platform/feedback.py",
    "scenara/infrastructure/postgres_feedback.py",
    "scenara/platform/control_plane.py",
    "scenara/infrastructure/postgres_control_plane.py",
    "migrations/0009_control_plane_records.sql",
    "migrations/0010_user_credentials.sql",
    "frontend/console/src/views/ResultsView.vue",
    "frontend/console/src/views/EnterpriseWorkspaceView.vue",
    "frontend/console/src/views/FeedbackView.vue",
    "frontend/console/src/views/GovernanceView.vue",
    "sdk/python/scenara_sdk/client.py",
    "sdk/typescript/src/generated.ts",
    "deploy/compose.yml",
    "deploy/OPERATIONS.md",
    "deploy/scripts/build-offline-bundle.sh",
    "deploy/scripts/install-offline.sh",
    "deploy/scripts/migrate.sh",
    "deploy/scripts/backup.sh",
    "deploy/scripts/restore.sh",
    "requirements/production.lock",
    "frontend/console/playwright.config.ts",
    "frontend/console/e2e/workspaces.spec.ts",
    "tests/test_control_plane.py",
    "docs/release/0.3.0-dev.11.md",
    "docs/release/SUPPORT_MATRIX.md",
    "docs/release/EVIDENCE_OWNERS.md",
    "docs/release/evidence/manifest.example.json",
)
REQUIRED_EVIDENCE_TYPES = {
    "backup_restore",
    "gpu_capacity",
    "integration_services",
    "model_rights",
    "ocr_evaluation",
    "offline_install",
    "portrait_evaluation",
    "security_assessment",
    "software_license_approval",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
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


def _timestamp(value: Any, field: str, evidence_type: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{evidence_type}: {field} is required")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{evidence_type}: {field} must be ISO-8601")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{evidence_type}: {field} must include a timezone")
        return None
    return parsed


def _required_values(metadata: dict[str, Any], names: set[str], evidence_type: str) -> list[str]:
    return [f"{evidence_type}: metadata.{name} is required" for name in sorted(names) if metadata.get(name) is None]


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_set(metadata: dict[str, Any], field: str, evidence_type: str, errors: list[str]) -> set[str]:
    value = metadata.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{evidence_type}: metadata.{field} must be a list of non-empty strings")
        return set()
    return set(value)


def _metadata_errors(evidence_type: str, metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if evidence_type in {"portrait_evaluation", "ocr_evaluation"}:
        if not metadata.get("dataset_version") or metadata.get("rights_cleared") is not True:
            errors.append(f"{evidence_type}: versioned and rights-cleared dataset evidence is required")
        if not isinstance(metadata.get("metrics"), dict) or not metadata["metrics"]:
            errors.append(f"{evidence_type}: fixed evaluation metrics are required")
        if metadata.get("thresholds_approved_before_run") is not True:
            errors.append(f"{evidence_type}: thresholds must be approved before evaluation")
        if _number(metadata.get("independent_runs"), 0) < 2 or metadata.get("within_tolerance") is not True:
            errors.append(f"{evidence_type}: two reproducible runs within approved tolerance are required")
    elif evidence_type == "gpu_capacity":
        if _number(metadata.get("gpu_memory_mib"), 0) < 23000:
            errors.append("gpu_capacity: target GPU must provide at least 23000 MiB")
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
        models = _string_set(metadata, "models", evidence_type, errors)
        if metadata.get("all_rights_cleared") is not True or not models:
            errors.append("model_rights: every production model must have cleared rights")
    elif evidence_type == "software_license_approval":
        errors.extend(_required_values(metadata, {"license_sha256", "approval_reference"}, evidence_type))
        if metadata.get("reviewed_by_legal") is not True:
            errors.append("software_license_approval: legal review must be confirmed")
    elif evidence_type == "offline_install":
        required = {"health", "console", "example_clients", "core_parse"}
        if metadata.get("blank_host") is not True or metadata.get("isolated_network") is not True:
            errors.append("offline_install: a blank isolated target host is required")
        checks = _string_set(metadata, "checks", evidence_type, errors)
        if metadata.get("checksums_verified") is not True or not required <= checks:
            errors.append("offline_install: checksums and all smoke checks must pass")
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
    release_identity: dict[str, str] | None = None,
    root: Path = ROOT,
) -> list[str]:
    if not isinstance(entry, dict):
        return ["evidence manifest entry must be an object"]
    evidence_type = str(entry.get("evidence_type", ""))
    errors: list[str] = []
    report_value = entry.get("report")
    report = (root / str(report_value)).resolve() if report_value else None
    reports_root = (root / "docs/release/evidence/reports").resolve()
    if evidence_type not in REQUIRED_EVIDENCE_TYPES:
        errors.append(f"unknown evidence type: {evidence_type or '<missing>'}")
    if report is not None and reports_root not in report.parents:
        errors.append(f"{evidence_type}: report must be inside docs/release/evidence/reports")
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
                    "approved_at",
                    "signed_by",
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
    executed_at = _timestamp(entry.get("executed_at"), "executed_at", evidence_type, errors)
    approved_at = _timestamp(entry.get("approved_at"), "approved_at", evidence_type, errors)
    if executed_at is not None and approved_at is not None and approved_at < executed_at:
        errors.append(f"{evidence_type}: approved_at cannot be earlier than executed_at")
    for field in ("signed_by", "target"):
        value = entry.get(field)
        if not isinstance(value, str) or not value or PLACEHOLDER.search(value):
            errors.append(f"{evidence_type}: {field} must be a non-placeholder value")
    if entry.get("status") != "passed":
        errors.append(f"{evidence_type}: status must be passed")
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        errors.append(f"{evidence_type}: metadata must be an object")
        metadata = {}
    errors.extend(_metadata_errors(evidence_type, metadata))
    if release_identity is not None and entry.get("release_identity") != release_identity:
        errors.append(f"{evidence_type}: release identity does not match the manifest")
    if evidence_type == "software_license_approval":
        license_path = root / "LICENSE"
        if license_path.is_file() and metadata.get("license_sha256") != digest(license_path):
            errors.append("software_license_approval: LICENSE SHA-256 does not match")
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
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.1":
        errors.append("release evidence manifest schema_version must be 1.1")
    if not isinstance(manifest, dict) or not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest.get("release", ""))):
        errors.append("release evidence manifest release must be a semantic version")
    release_identity_value = manifest.get("release_identity") if isinstance(manifest, dict) else None
    release_identity: dict[str, str] | None = None
    if not isinstance(release_identity_value, dict):
        errors.append("release evidence manifest release_identity must be an object")
    else:
        release_identity = {key: str(release_identity_value.get(key, "")) for key in RELEASE_IDENTITY_FIELDS}
        if set(release_identity_value) != RELEASE_IDENTITY_FIELDS:
            errors.append("release identity must contain exactly the required artifact fields")
        if not SOURCE_COMMIT.fullmatch(release_identity["source_commit"]):
            errors.append("release identity source_commit must be a full lowercase Git SHA")
        if expected_source_commit is not None and release_identity["source_commit"] != expected_source_commit:
            errors.append("release identity source_commit does not match the checked-out commit")
        if not IMAGE_DIGEST.fullmatch(release_identity["image_digest"]):
            errors.append("release identity image_digest must be a sha256 container digest")
        for field in ("offline_bundle_sha256", "openapi_sha256", "model_set_sha256"):
            if not SHA256.fullmatch(release_identity[field]):
                errors.append(f"release identity {field} must be a lowercase SHA-256")
        openapi = root / "docs/openapi.json"
        if openapi.is_file() and release_identity["openapi_sha256"] != digest(openapi):
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
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Scenara implementation and 1.0 release evidence")
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
