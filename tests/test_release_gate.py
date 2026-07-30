from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.release_gate import REQUIRED_EVIDENCE_TYPES, evidence_errors, implementation_errors


def test_release_implementation_gate_is_complete() -> None:
    assert implementation_errors() == []


def test_release_evidence_gate_fails_closed_without_manifest(tmp_path: Path) -> None:
    errors = evidence_errors(tmp_path / "missing.json")
    assert errors == [f"release evidence manifest is missing: {tmp_path / 'missing.json'}"]


def valid_metadata(evidence_type: str) -> dict[str, object]:
    values: dict[str, dict[str, object]] = {
        "portrait_evaluation": {
            "dataset_version": "portrait-1.0.0",
            "rights_cleared": True,
            "metrics": {"map": 0.9},
            "thresholds_approved_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
        },
        "ocr_evaluation": {
            "dataset_version": "ocr-1.0.0",
            "rights_cleared": True,
            "metrics": {"cer": 0.01},
            "thresholds_approved_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
        },
        "gpu_capacity": {
            "gpu_memory_mib": 24576,
            "scenarios": ["sustained_load", "burst", "vram_pressure", "backpressure", "recovery"],
            "p50_ms": 10,
            "p95_ms": 20,
            "p99_ms": 30,
            "throughput_per_second": 5,
            "error_rate": 0,
            "peak_vram_mib": 22000,
        },
        "integration_services": {
            "services": ["postgres_pgvector", "redis", "minio"],
            "skipped_tests": 0,
            "duplicate_logical_results": 0,
            "redis_rebuild_verified": True,
        },
        "security_assessment": {
            "scenarios": [
                "audit_fail_closed",
                "authorization",
                "biometric_deletion",
                "credential_redaction",
                "malicious_media",
                "ssrf",
            ]
        },
        "model_rights": {"all_rights_cleared": True, "models": ["portrait-1.0.0"]},
        "offline_install": {
            "blank_host": True,
            "isolated_network": True,
            "checksums_verified": True,
            "checks": ["health", "console", "example_clients", "core_parse"],
        },
        "backup_restore": {
            "rpo_hours": 24,
            "rto_hours": 4,
            "entities_verified": [
                "tenants",
                "projects",
                "media",
                "runs",
                "results",
                "pipelines",
                "models",
                "audit",
                "biometrics",
            ],
        },
    }
    return values[evidence_type]


def write_valid_manifest(root: Path) -> tuple[Path, dict[str, object]]:
    reports = root / "docs/release/evidence/reports"
    reports.mkdir(parents=True)
    entries: list[dict[str, object]] = []
    for evidence_type in sorted(REQUIRED_EVIDENCE_TYPES):
        report = reports / f"{evidence_type}.json"
        entry: dict[str, object] = {
            "evidence_type": evidence_type,
            "report": report.relative_to(root).as_posix(),
            "status": "passed",
            "executed_at": "2026-07-30T01:00:00Z",
            "approved_at": "2026-07-30T02:00:00Z",
            "signed_by": "测试负责人（仅单元测试）",
            "target": "qualification-target",
            "metadata": valid_metadata(evidence_type),
        }
        report.write_text(
            json.dumps({"schema_version": "1.0", **entry}, ensure_ascii=False),
            encoding="utf-8",
        )
        entry["sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
        entries.append(entry)
    manifest: dict[str, object] = {"schema_version": "1.0", "release": "1.0.0", "entries": entries}
    manifest_path = root / "docs/release/evidence/manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path, manifest


def test_release_evidence_gate_accepts_complete_structured_reports(tmp_path: Path) -> None:
    manifest_path, _ = write_valid_manifest(tmp_path)
    assert evidence_errors(manifest_path, root=tmp_path) == []


def test_release_evidence_gate_rejects_duplicate_and_placeholder_signatures(tmp_path: Path) -> None:
    manifest_path, manifest = write_valid_manifest(tmp_path)
    entries = manifest["entries"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    first["signed_by"] = "<name and role>"
    entries.append(dict(first))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = evidence_errors(manifest_path, root=tmp_path)
    assert any("signed_by must be a non-placeholder value" in error for error in errors)
    assert any("duplicate release evidence type" in error for error in errors)


def test_release_evidence_gate_rejects_malformed_metadata_collections(tmp_path: Path) -> None:
    manifest_path, manifest = write_valid_manifest(tmp_path)
    entries = manifest["entries"]
    assert isinstance(entries, list)
    gpu = next(entry for entry in entries if entry["evidence_type"] == "gpu_capacity")
    assert isinstance(gpu, dict)
    metadata = gpu["metadata"]
    assert isinstance(metadata, dict)
    metadata["scenarios"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = evidence_errors(manifest_path, root=tmp_path)

    assert "gpu_capacity: metadata.scenarios must be a list of non-empty strings" in errors
    assert "gpu_capacity: all capacity and recovery scenarios are required" in errors
