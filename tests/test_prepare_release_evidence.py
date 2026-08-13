from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.prepare_release_evidence import generate_report


def write_manifest(root: Path, evidence_type: str, *, status: str = "pending") -> Path:
    openapi = root / "docs/openapi.json"
    openapi.parent.mkdir(parents=True, exist_ok=True)
    openapi.write_text("{}\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.2",
        "release": "0.3.0-dev.20",
        "release_identity": {
            "source_commit": None,
            "image_digest": None,
            "offline_bundle_sha256": None,
            "openapi_sha256": hashlib.sha256(openapi.read_bytes()).hexdigest(),
            "model_set_sha256": None,
        },
        "entries": [{"evidence_type": evidence_type, "status": status}],
    }
    path = root / "docs/release/evidence/manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def gpu_result(root: Path, memory: int = 8192) -> Path:
    scenario_results = {}
    for name in ["sustained_load", "burst", "vram_pressure", "backpressure", "recovery"]:
        output = write_json(
            root / f"{name}.json",
            {"scenario": name, "exit_code": 0, "samples": [1, 2, 3]},
        )
        scenario_results[name] = {"exit_code": 0, "output_path": output.name}
    return write_json(
        root / f"gpu-{memory}.json",
        {
            "schema_version": "1.0",
            "evidence_type": "gpu_capacity",
            "device": {"name": f"NVIDIA measured {memory} MiB", "driver_version": "575.57"},
            "measurement": {
                "gpu_memory_mib": memory,
                "scenarios": list(scenario_results),
                "scenario_results": scenario_results,
                "p50_ms": 10,
                "p95_ms": 20,
                "p99_ms": 30,
                "throughput_per_second": 4,
                "error_rate": 0,
                "peak_vram_mib": min(memory, 4000),
                "command": "python capacity.py --duration 60",
                "duration_seconds": 60,
            },
        },
    )


def test_generate_report_inherits_identity_and_accepts_measured_gpu_at_any_capacity(tmp_path: Path) -> None:
    for memory in (8192, 49152):
        manifest_path = write_manifest(tmp_path, "gpu_capacity")
        raw_path = gpu_result(tmp_path, memory)
        output = tmp_path / f"candidate-{memory}.json"

        generate_report(
            "gpu_capacity",
            raw_path,
            "Ubuntu 24.04 qualification host",
            output,
            manifest_path,
            executed_at="2026-08-13T01:00:00Z",
        )

        report = json.loads(output.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert report["release_identity"] == manifest["release_identity"]
        assert report["metadata"]["gpu_memory_mib"] == memory


def test_generate_report_rejects_incomplete_gpu_facts_without_output(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "gpu_capacity")
    raw_path = write_json(
        tmp_path / "gpu.json",
        {
            "schema_version": "1.0",
            "evidence_type": "gpu_capacity",
            "device": {"memory_total_mib": 8192},
        },
    )
    output = tmp_path / "candidate.json"

    with pytest.raises(ValueError, match="scenario_results|gpu_memory_mib"):
        generate_report("gpu_capacity", raw_path, "local laptop GPU", output, manifest_path)

    assert not output.exists()


def test_generate_report_refuses_to_replace_completed_evidence(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "gpu_capacity", status="passed")
    raw_path = write_json(tmp_path / "gpu.json", {})

    with pytest.raises(ValueError, match="already completed"):
        generate_report("gpu_capacity", raw_path, "qualification target", tmp_path / "candidate.json", manifest_path)


def test_generate_report_requires_two_real_evaluation_runs(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "portrait_evaluation")
    dataset = write_json(
        tmp_path / "dataset.json",
        {"dataset_version": "portrait-1.0.0", "rights_cleared": True, "items": 20},
    )
    run_paths = []
    for index, run_id in enumerate(("run-a", "run-b")):
        run_paths.append(
            write_json(
                tmp_path / f"{run_id}.json",
                {"run_id": run_id, "executed_at": f"2026-08-13T01:{index:02d}:00Z", "exit_code": 0, "metrics": {"map": 0.9}},
            )
        )
    thresholds = write_json(
        tmp_path / "portrait-thresholds.json",
        {"fixed_at": "2026-08-12T01:00:00Z", "thresholds": {"map_min": 0.8}, "tolerances": {"map": 0.01}},
    )
    raw_path = write_json(
        tmp_path / "portrait.json",
        {
            "schema_version": "1.0",
            "evidence_type": "portrait_evaluation",
            "dataset_manifest_path": dataset.name,
            "thresholds_path": thresholds.name,
            "command": "python evaluate.py --dataset portrait-1.0.0",
            "runs": [{"output_path": path.name} for path in run_paths],
        },
    )
    output = tmp_path / "portrait-report.json"

    generate_report(
        "portrait_evaluation",
        raw_path,
        "isolated evaluation host",
        output,
        manifest_path,
        executed_at="2026-08-13T01:00:00Z",
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["independent_runs"] == 2
    assert report["metadata"]["dataset_manifest_sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()


def test_generate_report_refuses_uncleared_model_rights_without_output(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "model_rights")
    raw_path = write_json(
        tmp_path / "rights.json",
        {"schema_version": "1.0", "evidence_type": "model_rights", "models": []},
    )
    output = tmp_path / "candidate.json"

    with pytest.raises(ValueError, match="non-empty list"):
        generate_report("model_rights", raw_path, "rights inventory host", output, manifest_path)
    assert not output.exists()


def test_generate_report_rejects_evaluation_below_fixed_threshold(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "ocr_evaluation")
    dataset = write_json(
        tmp_path / "ocr-dataset.json",
        {"dataset_version": "ocr-1.0.0", "rights_cleared": True, "items": 20},
    )
    runs = []
    for index, run_id in enumerate(("ocr-a", "ocr-b")):
        output = write_json(
            tmp_path / f"{run_id}.json",
            {"run_id": run_id, "executed_at": f"2026-08-13T01:{index:02d}:00Z", "exit_code": 0, "metrics": {"accuracy": 0.7}},
        )
        runs.append({"output_path": output.name})
    thresholds = write_json(
        tmp_path / "ocr-thresholds.json",
        {"fixed_at": "2026-08-12T01:00:00Z", "thresholds": {"accuracy_min": 0.8}, "tolerances": {"accuracy": 0.01}},
    )
    raw_path = write_json(
        tmp_path / "ocr.json",
        {
            "schema_version": "1.0",
            "evidence_type": "ocr_evaluation",
            "dataset_manifest_path": dataset.name,
            "thresholds_path": thresholds.name,
            "command": "python evaluate_ocr.py --dataset ocr-1.0.0",
            "runs": runs,
        },
    )
    output = tmp_path / "ocr-report.json"

    with pytest.raises(ValueError, match="fails accuracy_min"):
        generate_report(
            "ocr_evaluation", raw_path, "isolated OCR host", output, manifest_path
        )
    assert not output.exists()


def test_generate_report_rejects_model_digest_not_bound_to_rights_record(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "model_rights")
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"qualified model bytes")
    rights = write_json(
        tmp_path / "model-rights.json",
        {
            "schema_version": "1.0",
            "evidence_type": "model_rights",
            "model_id": "scenara.portrait.detector",
            "model_version": "1.0.0",
            "artifact_sha256": "0" * 64,
            "license_identifier": "Apache-2.0",
            "license_source_uri": "https://spdx.org/licenses/Apache-2.0.html",
            "source_uri": "internal://models/portrait-detector-1.0.0",
            "intended_use_allowed": True,
            "redistribution_allowed": True,
            "rights_cleared": True,
            "source_identity_verified": True,
        },
    )
    raw_path = write_json(
        tmp_path / "rights-input.json",
        {
            "schema_version": "1.0",
            "evidence_type": "model_rights",
            "models": [
                {"artifact_path": artifact.name, "rights_record_path": rights.name}
            ]
        },
    )
    output = tmp_path / "rights-report.json"

    with pytest.raises(ValueError, match="artifact digest does not match rights record"):
        generate_report("model_rights", raw_path, "rights inventory host", output, manifest_path)
    assert not output.exists()


def test_generate_report_derives_offline_install_digests_and_accepts_small_gpu(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, "offline_install")
    bundle = tmp_path / "scenara-offline.tar.gz"
    bundle.write_bytes(b"offline bundle")
    installer_output = tmp_path / "installer.json"
    write_json(
        installer_output,
        {
            "schema_version": "1.0",
            "evidence_type": "offline_install",
            "installer_exit_code": 0,
            "checksums_verified": True,
            "host": {
                "host_os": "ubuntu",
                "host_version": "24.04",
                "gpu_memory_mib": 4096,
            },
            "services": {
                name: "running"
                for name in (
                    "api",
                    "batch-worker",
                    "stream-worker",
                    "scheduler",
                    "postgres",
                    "redis",
                    "minio",
                )
            },
            "installer_checks": {"health": "passed", "console": "passed"},
        },
    )
    source_commit = tmp_path / "source-commit.txt"
    source_commit.write_text("a" * 40 + "\n", encoding="utf-8")
    check_results = {}
    for check in ("example_clients", "core_parse"):
        check_output = write_json(
            tmp_path / f"{check}.json",
            {"check": check, "exit_code": 0},
        )
        check_results[check] = {"exit_code": 0, "output_path": check_output.name}
    raw_path = write_json(
        tmp_path / "offline.json",
        {
            "schema_version": "1.0",
            "evidence_type": "offline_install",
            "blank_host": True,
            "isolated_network": True,
            "bundle_path": bundle.name,
            "installer_result_path": installer_output.name,
            "source_commit_path": source_commit.name,
            "check_results": check_results,
        },
    )
    output = tmp_path / "offline-report.json"

    generate_report(
        "offline_install",
        raw_path,
        "isolated blank Ubuntu host",
        output,
        manifest_path,
        executed_at="2026-08-13T01:00:00Z",
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["gpu_memory_mib"] == 4096
    assert report["metadata"]["bundle_sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert report["metadata"]["checksums_verified"] is True
