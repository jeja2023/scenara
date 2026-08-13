from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.record_release_evidence import record_evidence


def write_manifest(root: Path) -> tuple[Path, dict[str, object]]:
    openapi = root / "docs/openapi.json"
    openapi.parent.mkdir(parents=True)
    openapi.write_text("{}\n", encoding="utf-8")
    identity = {
        "source_commit": None,
        "image_digest": None,
        "offline_bundle_sha256": None,
        "openapi_sha256": hashlib.sha256(openapi.read_bytes()).hexdigest(),
        "model_set_sha256": None,
    }
    manifest: dict[str, object] = {
        "schema_version": "1.2",
        "release": "0.3.0-dev.20",
        "release_identity": identity,
        "entries": [{"evidence_type": "security_assessment", "status": "pending"}],
    }
    path = root / "docs/release/evidence/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, manifest


def security_report(identity: object) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "evidence_type": "security_assessment",
        "status": "passed",
        "executed_at": "2026-08-13T01:00:00Z",
        "target": "isolated security test target",
        "release_identity": identity,
        "metadata": {
            "scenarios": [
                "audit_fail_closed",
                "authorization",
                "biometric_deletion",
                "credential_redaction",
                "malicious_media",
                "ssrf",
            ]
        },
    }


def test_record_evidence_writes_report_digest_and_manifest_entry(tmp_path: Path) -> None:
    manifest_path, manifest = write_manifest(tmp_path)
    input_path = tmp_path / "security-input.json"
    input_path.write_text(
        json.dumps(security_report(manifest["release_identity"])),
        encoding="utf-8",
    )

    report_path = record_evidence(input_path, manifest_path, root=tmp_path)

    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = updated["entries"][0]
    assert report_path == tmp_path / "docs/release/evidence/reports/security-assessment.json"
    assert entry["status"] == "passed"
    assert entry["sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert json.loads(report_path.read_text(encoding="utf-8"))["metadata"] == entry["metadata"]


def test_record_evidence_rejects_pending_reports_without_mutation(tmp_path: Path) -> None:
    manifest_path, manifest = write_manifest(tmp_path)
    original = manifest_path.read_bytes()
    report = security_report(manifest["release_identity"])
    report["status"] = "pending"
    input_path = tmp_path / "security-input.json"
    input_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="only completed passed evidence"):
        record_evidence(input_path, manifest_path, root=tmp_path)

    assert manifest_path.read_bytes() == original
    assert not (tmp_path / "docs/release/evidence/reports/security-assessment.json").exists()


def test_record_evidence_restores_existing_report_when_validation_fails(tmp_path: Path) -> None:
    manifest_path, manifest = write_manifest(tmp_path)
    report_path = tmp_path / "docs/release/evidence/reports/security-assessment.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("previous report\n", encoding="utf-8")
    report = security_report(manifest["release_identity"])
    report["target"] = "<target>"
    input_path = tmp_path / "security-input.json"
    input_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="target must be a non-placeholder value"):
        record_evidence(input_path, manifest_path, root=tmp_path)

    assert report_path.read_text(encoding="utf-8") == "previous report\n"


def test_record_evidence_refuses_to_replace_completed_entry(tmp_path: Path) -> None:
    manifest_path, manifest = write_manifest(tmp_path)
    manifest["entries"] = [
        {"evidence_type": "security_assessment", "status": "passed"}
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    input_path = tmp_path / "security-input.json"
    input_path.write_text(
        json.dumps(security_report(manifest["release_identity"])), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="already completed"):
        record_evidence(input_path, manifest_path, root=tmp_path)
