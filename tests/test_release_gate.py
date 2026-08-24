from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.release_gate import (
    REQUIRED_EVIDENCE_TYPES,
    evidence_errors,
    implementation_errors,
    license_errors,
)


def test_release_implementation_gate_is_complete() -> None:
    assert implementation_errors() == []


def test_release_evidence_gate_fails_closed_without_manifest(tmp_path: Path) -> None:
    errors = evidence_errors(tmp_path / "missing.json")
    assert errors == [f"release evidence manifest is missing: {tmp_path / 'missing.json'}"]


def valid_metadata(evidence_type: str) -> dict[str, object]:
    values: dict[str, dict[str, object]] = {
        "portrait_evaluation": {
            "dataset_version": "portrait-1.0.0",
            "dataset_manifest_sha256": "1" * 64,
            "rights_cleared": True,
            "metrics": {"map": 0.9},
            "thresholds": {"map_min": 0.8},
            "tolerances": {"map": 0.01},
            "thresholds_sha256": "0" * 64,
            "thresholds_fixed_at": "2026-07-29T01:00:00Z",
            "thresholds_fixed_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
            "command": "python evaluate_portrait.py --dataset portrait-1.0.0",
            "runs": [
                {"run_id": "portrait-a", "executed_at": "2026-07-30T00:00:00Z", "exit_code": 0, "output_sha256": "2" * 64, "metrics": {"map": 0.9}},
                {"run_id": "portrait-b", "executed_at": "2026-07-30T00:30:00Z", "exit_code": 0, "output_sha256": "3" * 64, "metrics": {"map": 0.9}},
            ],
        },
        "ocr_evaluation": {
            "dataset_version": "ocr-1.0.0",
            "dataset_manifest_sha256": "4" * 64,
            "rights_cleared": True,
            "metrics": {"cer": 0.01},
            "thresholds": {"cer_max": 0.02},
            "tolerances": {"cer": 0.001},
            "thresholds_sha256": "0" * 64,
            "thresholds_fixed_at": "2026-07-29T01:00:00Z",
            "thresholds_fixed_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
            "command": "python evaluate_ocr.py --dataset ocr-1.0.0",
            "runs": [
                {"run_id": "ocr-a", "executed_at": "2026-07-30T00:00:00Z", "exit_code": 0, "output_sha256": "5" * 64, "metrics": {"cer": 0.01}},
                {"run_id": "ocr-b", "executed_at": "2026-07-30T00:30:00Z", "exit_code": 0, "output_sha256": "6" * 64, "metrics": {"cer": 0.01}},
            ],
        },
        "behavior_evaluation": {
            "dataset_version": "behavior-1.0.0",
            "dataset_manifest_sha256": "a" * 64,
            "rights_cleared": True,
            "metrics": {"action_f1": 0.9, "temporal_iou": 0.8},
            "thresholds": {"action_f1_min": 0.85, "temporal_iou_min": 0.75},
            "tolerances": {"action_f1": 0.01, "temporal_iou": 0.01},
            "thresholds_sha256": "b" * 64,
            "thresholds_fixed_at": "2026-07-29T01:00:00Z",
            "thresholds_fixed_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
            "command": "python evaluate_behavior.py --dataset behavior-1.0.0",
            "runs": [
                {"run_id": "behavior-a", "executed_at": "2026-07-30T00:00:00Z", "exit_code": 0, "output_sha256": "c" * 64, "metrics": {"action_f1": 0.9, "temporal_iou": 0.8}},
                {"run_id": "behavior-b", "executed_at": "2026-07-30T00:30:00Z", "exit_code": 0, "output_sha256": "d" * 64, "metrics": {"action_f1": 0.9, "temporal_iou": 0.8}},
            ],
        },
        "fashion_evaluation": {
            "dataset_version": "fashion-1.0.0",
            "dataset_manifest_sha256": "a" * 64,
            "rights_cleared": True,
            "metrics": {"macro_f1": 0.9, "map50": 0.8},
            "thresholds": {"macro_f1_min": 0.85, "map50_min": 0.75},
            "tolerances": {"macro_f1": 0.01, "map50": 0.01},
            "thresholds_sha256": "b" * 64,
            "thresholds_fixed_at": "2026-07-29T01:00:00Z",
            "thresholds_fixed_before_run": True,
            "independent_runs": 2,
            "within_tolerance": True,
            "command": "python evaluate_fashion.py --dataset fashion-1.0.0",
            "runs": [
                {"run_id": "fashion-a", "executed_at": "2026-07-30T00:00:00Z", "exit_code": 0, "output_sha256": "c" * 64, "metrics": {"macro_f1": 0.9, "map50": 0.8}},
                {"run_id": "fashion-b", "executed_at": "2026-07-30T00:30:00Z", "exit_code": 0, "output_sha256": "d" * 64, "metrics": {"macro_f1": 0.9, "map50": 0.8}},
            ],
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
            "gpu_name": "NVIDIA RTX qualification GPU",
            "driver_version": "575.57",
            "command": "python capacity.py --duration 3600",
            "duration_seconds": 3600,
            "raw_result_sha256": "7" * 64,
            "scenario_results": {
                name: {
                    "status": "passed",
                    "exit_code": 0,
                    "output_sha256": "f" * 64,
                }
                for name in ["sustained_load", "burst", "vram_pressure", "backpressure", "recovery"]
            },
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
        "model_rights": {
            "all_rights_cleared": True,
            "models": [
                {
                    "model_id": "scenara.portrait.detector",
                    "model_version": "1.0.0",
                    "artifact_sha256": "e" * 64,
                    "license_identifier": "LicenseRef-Test-Model",
                    "license_source_uri": "https://spdx.org/licenses/Apache-2.0.html",
                    "source_uri": "internal://models/portrait-detector-1.0.0",
                    "rights_record_sha256": "8" * 64,
                    "intended_use_allowed": True,
                    "redistribution_allowed": True,
                    "rights_cleared": True,
                    "source_identity_verified": True,
                }
            ],
        },
        "software_license": {
            "license_sha256": "set-by-fixture",
            "license_identifier": "MIT",
            "review_basis": "personal_project_self_review",
            "review_scope": [
                "compliance",
                "copyright_and_ownership",
                "grant_and_restrictions",
                "termination",
                "third_party_materials",
                "warranty_and_liability",
            ],
        },
        "offline_install": {
            "blank_host": True,
            "isolated_network": True,
            "checksums_verified": True,
            "checks": ["health", "console", "example_clients", "core_parse"],
            "host_os": "ubuntu",
            "host_version": "24.04",
            "gpu_memory_mib": 24576,
            "bundle_sha256": "9" * 64,
            "installer_output_sha256": "a" * 64,
            "installer_exit_code": 0,
            "source_commit": "b" * 40,
            "services": {
                name: "running"
                for name in ["api", "batch-worker", "stream-worker", "scheduler", "postgres", "redis", "minio"]
            },
            "check_results": {
                name: {
                    "status": "passed",
                    "exit_code": 0,
                    "output_sha256": "d" * 64,
                }
                for name in ["health", "console", "example_clients", "core_parse"]
            },
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
    license_path = root / "LICENSE"
    license_path.write_text("Scenara approved test license\n", encoding="utf-8")
    openapi_path = root / "docs/openapi.json"
    openapi_path.write_text("{}\n", encoding="utf-8")
    release_identity = {
        "source_commit": "a" * 40,
        "image_digest": "sha256:" + "b" * 64,
        "offline_bundle_sha256": "c" * 64,
        "openapi_sha256": hashlib.sha256(openapi_path.read_bytes()).hexdigest(),
        "model_set_sha256": "d" * 64,
    }
    entries: list[dict[str, object]] = []
    for evidence_type in sorted(REQUIRED_EVIDENCE_TYPES):
        report = reports / f"{evidence_type}.json"
        metadata = valid_metadata(evidence_type)
        if evidence_type == "software_license":
            metadata["license_sha256"] = hashlib.sha256(license_path.read_bytes()).hexdigest()
        entry: dict[str, object] = {
            "evidence_type": evidence_type,
            "report": report.relative_to(root).as_posix(),
            "status": "passed",
            "executed_at": "2026-07-30T01:00:00Z",
            "target": "qualification-target",
            "release_identity": release_identity,
            "metadata": metadata,
        }
        report.write_text(
            json.dumps({"schema_version": "1.0", **entry}, ensure_ascii=False),
            encoding="utf-8",
        )
        entry["sha256"] = hashlib.sha256(report.read_bytes()).hexdigest()
        entries.append(entry)
    manifest: dict[str, object] = {
        "schema_version": "1.2",
        "release": "1.0.0",
        "release_identity": release_identity,
        "entries": entries,
    }
    manifest_path = root / "docs/release/evidence/manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return manifest_path, manifest


def test_release_evidence_gate_accepts_complete_structured_reports(tmp_path: Path) -> None:
    manifest_path, _ = write_valid_manifest(tmp_path)
    assert evidence_errors(manifest_path, root=tmp_path, expected_source_commit="a" * 40) == []


def test_release_evidence_gate_binds_reports_to_the_checked_out_release(tmp_path: Path) -> None:
    manifest_path, manifest = write_valid_manifest(tmp_path)
    errors = evidence_errors(manifest_path, root=tmp_path, expected_source_commit="f" * 40)
    assert "release identity source_commit does not match the checked-out commit" in errors

    entries = manifest["entries"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    entry["release_identity"] = {**entry["release_identity"], "model_set_sha256": "e" * 64}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = evidence_errors(manifest_path, root=tmp_path, expected_source_commit="a" * 40)
    assert any("release identity does not match the manifest" in error for error in errors)


def test_strict_release_rejects_placeholder_software_license(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "This license is an engineering placeholder and must receive legal review.",
        encoding="utf-8",
    )
    assert license_errors(tmp_path) == [
        "software license still contains the engineering legal-review placeholder"
    ]


def test_release_evidence_gate_rejects_duplicate_and_placeholder_targets(tmp_path: Path) -> None:
    manifest_path, manifest = write_valid_manifest(tmp_path)
    entries = manifest["entries"]
    assert isinstance(entries, list)
    first = entries[0]
    assert isinstance(first, dict)
    first["target"] = "<target>"
    entries.append(dict(first))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    errors = evidence_errors(manifest_path, root=tmp_path)
    assert any("target must be a non-placeholder value" in error for error in errors)
    assert any("duplicate release evidence type" in error for error in errors)


def test_release_evidence_manifest_can_track_pending_personal_project_work(tmp_path: Path) -> None:
    manifest_path = tmp_path / "docs/release/evidence/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.2",
                "release": "0.3.0-dev.20",
                "release_identity": {
                    "source_commit": None,
                    "image_digest": None,
                    "offline_bundle_sha256": None,
                    "openapi_sha256": None,
                    "model_set_sha256": None,
                },
                "entries": [
                    {"evidence_type": evidence_type, "status": "pending"}
                    for evidence_type in sorted(REQUIRED_EVIDENCE_TYPES)
                ],
            }
        ),
        encoding="utf-8",
    )

    errors = evidence_errors(manifest_path, root=tmp_path)

    assert errors == [
        "pending release evidence: " + ", ".join(sorted(REQUIRED_EVIDENCE_TYPES))
    ]


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


def test_release_evidence_gate_requires_objective_model_rights_records(tmp_path: Path) -> None:
    manifest_path, manifest = write_valid_manifest(tmp_path)
    entries = manifest["entries"]
    assert isinstance(entries, list)
    model_rights = next(entry for entry in entries if entry["evidence_type"] == "model_rights")
    assert isinstance(model_rights, dict)
    model_rights["metadata"] = {"all_rights_cleared": True, "models": ["portrait-1.0.0"]}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors = evidence_errors(manifest_path, root=tmp_path)

    assert "model_rights: metadata.models[0] must be an object" in errors
