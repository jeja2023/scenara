from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_gate import REQUIRED_EVIDENCE_TYPES, validate_entry  # noqa: E402


EVALUATION_TYPES = {"portrait_evaluation", "ocr_evaluation"}
GPU_SCENARIOS = {"sustained_load", "burst", "vram_pressure", "backpressure", "recovery"}
OFFLINE_SERVICES = {"api", "batch-worker", "stream-worker", "scheduler", "postgres", "redis", "minio"}
QUALIFICATION_EVIDENCE_TYPES = EVALUATION_TYPES | {
    "gpu_capacity",
    "model_rights",
    "offline_install",
}


def _read_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description} must be readable UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a JSON object: {path}")
    return value


def _render(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _required_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _required_sha256(value: Any, name: str) -> str:
    value = _required_string(value, name)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _input_file(value: Any, base_dir: Path, name: str) -> Path:
    raw_path = _required_string(value, name)
    path = Path(raw_path)
    if not path.is_absolute():
        path = base_dir / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{name} must name a readable file: {path}")
    return path


def _file_sha256(value: Any, base_dir: Path, name: str) -> str:
    return hashlib.sha256(_input_file(value, base_dir, name).read_bytes()).hexdigest()


def _input_object(value: Any, base_dir: Path, name: str) -> tuple[Path, dict[str, Any]]:
    path = _input_file(value, base_dir, name)
    return path, _read_object(path, name)


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _iso_timestamp(value: Any, name: str) -> datetime:
    raw = _required_string(value, name)
    try:
        timestamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} must be a valid ISO-8601 timestamp") from None
    if timestamp.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return timestamp


def _evaluation_passes(
    metrics: dict[str, Any],
    runs: list[dict[str, Any]],
    thresholds: dict[str, Any],
    tolerances: dict[str, Any],
    evidence_type: str,
) -> None:
    checked_metrics: set[str] = set()
    for threshold_name, threshold_value in thresholds.items():
        if threshold_name.endswith("_min"):
            metric_name = threshold_name[:-4]
            minimum = True
        elif threshold_name.endswith("_max"):
            metric_name = threshold_name[:-4]
            minimum = False
        else:
            raise ValueError(
                f"{evidence_type}: threshold {threshold_name} must end in _min or _max"
            )
        limit = _number(threshold_value, f"{evidence_type}: thresholds.{threshold_name}")
        measured_values = [metrics.get(metric_name)] + [run["metrics"].get(metric_name) for run in runs]
        for index, measured_value in enumerate(measured_values):
            measured = _number(measured_value, f"{evidence_type}: metric {metric_name}")
            if (minimum and measured < limit) or (not minimum and measured > limit):
                source = "aggregate" if index == 0 else f"run {runs[index - 1]['run_id']}"
                raise ValueError(
                    f"{evidence_type}: {source} metric {metric_name} fails {threshold_name}={limit}"
                )
        checked_metrics.add(metric_name)

    if set(tolerances) != checked_metrics:
        raise ValueError(
            f"{evidence_type}: tolerances must cover exactly the threshold metrics"
        )
    for metric_name, tolerance_value in tolerances.items():
        tolerance = _number(tolerance_value, f"{evidence_type}: tolerances.{metric_name}")
        if tolerance < 0:
            raise ValueError(f"{evidence_type}: tolerance for {metric_name} must be non-negative")
        values = [
            _number(run["metrics"].get(metric_name), f"{evidence_type}: metric {metric_name}")
            for run in runs
        ]
        if max(values) - min(values) > tolerance:
            raise ValueError(
                f"{evidence_type}: independent runs exceed tolerance for {metric_name}"
            )


def _normalize_evaluation(
    raw: dict[str, Any], evidence_type: str, base_dir: Path
) -> dict[str, Any]:
    dataset_path, dataset = _input_object(
        raw.get("dataset_manifest_path"),
        base_dir,
        f"{evidence_type}: dataset_manifest_path",
    )
    dataset_version = _required_string(
        dataset.get("dataset_version"), f"{evidence_type}: dataset_version"
    )
    dataset_manifest_sha256 = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    if dataset.get("rights_cleared") is not True:
        raise ValueError(f"{evidence_type}: dataset rights_cleared must be true")
    thresholds_path, threshold_document = _input_object(
        raw.get("thresholds_path"),
        base_dir,
        f"{evidence_type}: thresholds_path",
    )
    thresholds = threshold_document.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ValueError(f"{evidence_type}: fixed thresholds are required")
    tolerances = threshold_document.get("tolerances")
    if not isinstance(tolerances, dict) or not tolerances:
        raise ValueError(f"{evidence_type}: fixed run tolerances are required")
    thresholds_fixed_at = _required_string(
        threshold_document.get("fixed_at"), f"{evidence_type}: thresholds.fixed_at"
    )
    fixed_at = _iso_timestamp(
        thresholds_fixed_at, f"{evidence_type}: thresholds.fixed_at"
    )
    runs = raw.get("runs")
    if not isinstance(runs, list) or len(runs) < 2:
        raise ValueError(f"{evidence_type}: at least two independent runs are required")
    normalized_runs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, run_value in enumerate(runs):
        run = _required_object(run_value, f"{evidence_type}: runs[{index}]")
        output_path, output = _input_object(
            run.get("output_path"),
            base_dir,
            f"{evidence_type}: runs[{index}].output_path",
        )
        if output.get("exit_code") != 0:
            raise ValueError(f"{evidence_type}: runs[{index}] did not exit successfully")
        executed_at = _required_string(
            output.get("executed_at"), f"{evidence_type}: runs[{index}].executed_at"
        )
        if _iso_timestamp(
            executed_at, f"{evidence_type}: runs[{index}].executed_at"
        ) <= fixed_at:
            raise ValueError(f"{evidence_type}: thresholds must be fixed before every run")
        run_id = _required_string(
            output.get("run_id"), f"{evidence_type}: runs[{index}].run_id"
        )
        if run_id in seen:
            raise ValueError(f"{evidence_type}: run ids must be unique")
        seen.add(run_id)
        output_sha256 = hashlib.sha256(output_path.read_bytes()).hexdigest()
        metrics = output.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError(f"{evidence_type}: runs[{index}].metrics are required")
        normalized_runs.append(
            {
                "run_id": run_id,
                "executed_at": executed_at,
                "exit_code": 0,
                "output_sha256": output_sha256,
                "metrics": metrics,
            }
        )
    threshold_metrics = {
        name[:-4] for name in thresholds if name.endswith(("_min", "_max"))
    }
    metrics = {
        name: sum(
            _number(run["metrics"].get(name), f"{evidence_type}: metric {name}")
            for run in normalized_runs
        )
        / len(normalized_runs)
        for name in sorted(threshold_metrics)
    }
    _evaluation_passes(metrics, normalized_runs, thresholds, tolerances, evidence_type)
    command = _required_string(raw.get("command"), f"{evidence_type}: command")
    return {
        "dataset_version": dataset_version,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "rights_cleared": True,
        "metrics": metrics,
        "thresholds": thresholds,
        "tolerances": tolerances,
        "thresholds_sha256": hashlib.sha256(thresholds_path.read_bytes()).hexdigest(),
        "thresholds_fixed_at": thresholds_fixed_at,
        "thresholds_fixed_before_run": True,
        "independent_runs": len(normalized_runs),
        "within_tolerance": True,
        "command": command,
        "runs": normalized_runs,
    }


def _normalize_gpu(
    raw: dict[str, Any], raw_result_sha256: str, base_dir: Path
) -> dict[str, Any]:
    device = raw.get("device", raw)
    measurement = raw.get("measurement", raw)
    device = _required_object(device, "gpu device")
    measurement = _required_object(measurement, "gpu measurement")
    memory = measurement.get("gpu_memory_mib", device.get("gpu_memory_mib", device.get("memory_total_mib")))
    try:
        memory = _number(memory, "gpu_capacity: gpu_memory_mib")
    except ValueError:
        raise ValueError("gpu_capacity: gpu_memory_mib must be a measured positive number") from None
    if memory <= 0:
        raise ValueError("gpu_capacity: gpu_memory_mib must be a measured positive number")
    scenarios = measurement.get("scenarios", sorted(GPU_SCENARIOS))
    if not isinstance(scenarios, list) or set(scenarios) != GPU_SCENARIOS:
        raise ValueError("gpu_capacity: all five required scenarios must be present")
    scenario_results = measurement.get("scenario_results")
    if not isinstance(scenario_results, dict) or set(scenario_results) != GPU_SCENARIOS:
        raise ValueError("gpu_capacity: scenario_results must cover all five scenarios")
    scenario_paths: set[Path] = set()
    for scenario in GPU_SCENARIOS:
        result = scenario_results[scenario]
        if not isinstance(result, dict):
            raise ValueError(f"gpu_capacity: scenario {scenario} did not pass")
        output_path, output = _input_object(
            result.get("output_path"),
            base_dir,
            f"gpu_capacity: scenario_results.{scenario}.output_path",
        )
        if output_path in scenario_paths:
            raise ValueError("gpu_capacity: scenario output files must be unique")
        scenario_paths.add(output_path)
        if output.get("scenario") != scenario or output.get("exit_code") != 0:
            raise ValueError(f"gpu_capacity: scenario {scenario} did not pass")
        normalized_result = {
            "status": "passed",
            "exit_code": 0,
            "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        }
        scenario_results[scenario] = normalized_result
    metadata = {
        **measurement,
        "gpu_memory_mib": memory,
        "scenarios": sorted(GPU_SCENARIOS),
        "scenario_results": scenario_results,
    }
    metadata["gpu_name"] = _required_string(device.get("gpu_name", device.get("name")), "gpu_capacity: gpu_name")
    metadata["driver_version"] = _required_string(device.get("driver_version"), "gpu_capacity: driver_version")
    metadata["command"] = _required_string(measurement.get("command"), "gpu_capacity: command")
    metadata["raw_result_sha256"] = raw_result_sha256
    return metadata


def _normalize_model_rights(raw: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    models = raw.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("model_rights: models must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for index, model_value in enumerate(models):
        reference = _required_object(model_value, f"model_rights: models[{index}]")
        rights_path, model = _input_object(
            reference.get("rights_record_path"),
            base_dir,
            f"model_rights: models[{index}].rights_record_path",
        )
        if model.get("schema_version") != "1.0" or model.get("evidence_type") != "model_rights":
            raise ValueError(f"model_rights: models[{index}] rights record identity is invalid")
        required = {
            "artifact_sha256",
            "model_id",
            "model_version",
            "license_identifier",
            "license_source_uri",
            "source_uri",
        }
        missing = sorted(name for name in required if not isinstance(model.get(name), str) or not model[name].strip())
        if missing:
            raise ValueError(f"model_rights: models[{index}] missing fields: {', '.join(missing)}")
        for name in ("intended_use_allowed", "redistribution_allowed", "rights_cleared", "source_identity_verified"):
            if model.get(name) is not True:
                raise ValueError(f"model_rights: models[{index}].{name} must be true")
        normalized_model = dict(model)
        artifact_sha256 = _file_sha256(
            reference.get("artifact_path"),
            base_dir,
            f"model_rights: models[{index}].artifact_path",
        )
        if _required_sha256(
            model.get("artifact_sha256"),
            f"model_rights: models[{index}].artifact_sha256",
        ) != artifact_sha256:
            raise ValueError(
                f"model_rights: models[{index}] artifact digest does not match rights record"
            )
        normalized_model["artifact_sha256"] = artifact_sha256
        normalized_model["rights_record_sha256"] = hashlib.sha256(
            rights_path.read_bytes()
        ).hexdigest()
        normalized.append(normalized_model)
    return {"all_rights_cleared": True, "models": normalized}


def _normalize_offline(raw: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    installer_path, installer_result = _input_object(
        raw.get("installer_result_path"),
        base_dir,
        "offline_install: installer_result_path",
    )
    if installer_result.get("schema_version") != "1.0" or installer_result.get(
        "evidence_type"
    ) != "offline_install":
        raise ValueError("offline_install: installer result identity is invalid")
    host = _required_object(installer_result.get("host"), "offline_install host")
    check_results = raw.get("check_results")
    required_checks = {"health", "console", "example_clients", "core_parse"}
    external_checks = {"example_clients", "core_parse"}
    if raw.get("blank_host") is not True or raw.get("isolated_network") is not True:
        raise ValueError("offline_install: blank_host and isolated_network must be true")
    if installer_result.get("installer_exit_code") != 0:
        raise ValueError("offline_install: installer did not exit successfully")
    if installer_result.get("checksums_verified") is not True:
        raise ValueError("offline_install: installer did not verify bundle checksums")
    installer_checks = installer_result.get("installer_checks")
    if not isinstance(installer_checks, dict) or any(
        installer_checks.get(check) != "passed" for check in {"health", "console"}
    ):
        raise ValueError("offline_install: installer health and console checks must pass")
    if not isinstance(check_results, dict) or set(check_results) != external_checks:
        raise ValueError(
            "offline_install: check_results must contain example_clients and core_parse"
        )
    installer_sha256 = hashlib.sha256(installer_path.read_bytes()).hexdigest()
    normalized_check_results: dict[str, dict[str, Any]] = {
        check: {
            "status": "passed",
            "exit_code": 0,
            "output_sha256": installer_sha256,
        }
        for check in ("health", "console")
    }
    check_paths: set[Path] = set()
    for check in sorted(external_checks):
        result = _required_object(check_results[check], f"offline_install: check_results.{check}")
        output_path, output = _input_object(
            result.get("output_path"),
            base_dir,
            f"offline_install: check_results.{check}.output_path",
        )
        if output_path in check_paths:
            raise ValueError("offline_install: smoke-check output files must be unique")
        check_paths.add(output_path)
        if output.get("check") != check or output.get("exit_code") != 0:
            raise ValueError(f"offline_install: check {check} did not pass")
        normalized_check_results[check] = {
            "status": "passed",
            "exit_code": 0,
            "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        }
    services = installer_result.get("services")
    if not isinstance(services, dict) or any(services.get(name) != "running" for name in OFFLINE_SERVICES):
        raise ValueError("offline_install: every required service must be running")
    host_os = host.get("host_os", host.get("os"))
    host_version = host.get("host_version", host.get("version"))
    if host_os != "ubuntu" or host_version != "24.04":
        raise ValueError("offline_install: target host must be Ubuntu 24.04")
    memory = host.get("gpu_memory_mib", raw.get("gpu_memory_mib"))
    try:
        memory = _number(memory, "offline_install: gpu_memory_mib")
    except ValueError:
        raise ValueError("offline_install: gpu_memory_mib must be a measured positive number") from None
    if memory <= 0:
        raise ValueError("offline_install: gpu_memory_mib must be a measured positive number")
    source_commit_path = _input_file(
        raw.get("source_commit_path"), base_dir, "offline_install: source_commit_path"
    )
    source_commit = source_commit_path.read_text(encoding="utf-8").strip()
    if len(source_commit) != 40 or any(char not in "0123456789abcdef" for char in source_commit):
        raise ValueError("offline_install: source_commit_path must contain a full lowercase Git SHA")
    excluded = {
        "bundle_path",
        "check_results",
        "evidence_type",
        "installer_result_path",
        "schema_version",
        "source_commit_path",
    }
    metadata = {key: value for key, value in raw.items() if key not in excluded}
    return {
        **metadata,
        "host_os": host_os,
        "host_version": host_version,
        "gpu_memory_mib": memory,
        "installer_exit_code": 0,
        "checksums_verified": True,
        "checks": sorted(required_checks),
        "check_results": normalized_check_results,
        "bundle_sha256": _file_sha256(
            raw.get("bundle_path"), base_dir, "offline_install: bundle_path"
        ),
        "installer_output_sha256": installer_sha256,
        "source_commit": source_commit,
        "services": services,
    }


def normalize_raw(
    evidence_type: str,
    raw: dict[str, Any],
    *,
    base_dir: Path,
    raw_result_sha256: str | None = None,
) -> dict[str, Any]:
    if evidence_type in EVALUATION_TYPES:
        return _normalize_evaluation(raw, evidence_type, base_dir)
    if evidence_type == "gpu_capacity":
        if raw_result_sha256 is None:
            raise ValueError("gpu_capacity: raw qualification result digest is required")
        return _normalize_gpu(raw, raw_result_sha256, base_dir)
    if evidence_type == "model_rights":
        return _normalize_model_rights(raw, base_dir)
    if evidence_type == "offline_install":
        return _normalize_offline(raw, base_dir)
    return raw


def _prepare_report(
    evidence_type: str,
    metadata_path: Path,
    target: str,
    output_path: Path,
    manifest_path: Path,
    *,
    executed_at: str | None = None,
) -> Path:
    if evidence_type not in REQUIRED_EVIDENCE_TYPES:
        raise ValueError(f"unknown evidence type: {evidence_type}")
    metadata = _read_object(metadata_path.resolve(), "evidence metadata")
    manifest = _read_object(manifest_path.resolve(), "release evidence manifest")
    release_identity = manifest.get("release_identity")
    if not isinstance(release_identity, dict):
        raise ValueError("release evidence manifest release_identity must be an object")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("release evidence manifest entries must be a list")
    matching = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("evidence_type") == evidence_type
    ]
    if len(matching) != 1:
        raise ValueError(f"manifest must contain exactly one {evidence_type} entry")
    if matching[0].get("status") != "pending":
        raise ValueError(f"{evidence_type} evidence is already completed")

    report = {
        "schema_version": "1.0",
        "evidence_type": evidence_type,
        "status": "passed",
        "executed_at": executed_at or datetime.now(UTC).isoformat(),
        "target": target,
        "release_identity": release_identity,
        "metadata": metadata,
    }
    content = _render(report)
    with tempfile.TemporaryDirectory(prefix="scenara-evidence-") as temporary_value:
        validation_root = Path(temporary_value)
        relative_report = Path("docs/release/evidence/reports") / f"{evidence_type}.json"
        validation_report = validation_root / relative_report
        validation_report.parent.mkdir(parents=True)
        validation_report.write_bytes(content)
        entry = {key: value for key, value in report.items() if key != "schema_version"}
        entry["report"] = relative_report.as_posix()
        entry["sha256"] = hashlib.sha256(content).hexdigest()
        errors = validate_entry(entry, release_identity=release_identity, root=validation_root)
    if errors:
        raise ValueError("invalid release evidence:\n" + "\n".join(errors))

    output_path = output_path.resolve()
    if output_path.exists():
        raise ValueError(f"refusing to overwrite existing output: {output_path}")
    _atomic_write(output_path, content)
    return output_path


def generate_report(
    evidence_type: str,
    raw_input_path: Path,
    target: str,
    output_path: Path,
    manifest_path: Path,
    *,
    executed_at: str | None = None,
) -> Path:
    """Normalize a real qualification result and emit a validated candidate.

    The output is written only after the normalized facts pass the same
    ``validate_entry`` contract used by the release gate.
    """
    if evidence_type not in QUALIFICATION_EVIDENCE_TYPES:
        raise ValueError(f"unsupported qualification evidence type: {evidence_type}")
    manifest = _read_object(manifest_path.resolve(), "release evidence manifest")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("release evidence manifest entries must be a list")
    matching = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("evidence_type") == evidence_type
    ]
    if len(matching) != 1:
        raise ValueError(f"manifest must contain exactly one {evidence_type} entry")
    if matching[0].get("status") != "pending":
        raise ValueError(f"{evidence_type} evidence is already completed")

    raw_input_path = raw_input_path.resolve()
    raw = _read_object(raw_input_path, "qualification result")
    if raw.get("schema_version") != "1.0":
        raise ValueError("qualification result schema_version must be 1.0")
    if raw.get("evidence_type") != evidence_type:
        raise ValueError("qualification result evidence_type does not match the command")
    raw_result_sha256 = hashlib.sha256(raw_input_path.read_bytes()).hexdigest()
    metadata = normalize_raw(
        evidence_type,
        raw,
        base_dir=raw_input_path.parent,
        raw_result_sha256=raw_result_sha256,
    )
    with tempfile.TemporaryDirectory(prefix="scenara-normalized-evidence-") as temporary_value:
        metadata_path = Path(temporary_value) / "metadata.json"
        metadata_path.write_bytes(_render(metadata))
        return _prepare_report(
            evidence_type, metadata_path, target, output_path, manifest_path, executed_at=executed_at
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a fail-closed report from raw qualification files"
    )
    parser.add_argument("evidence_type", choices=sorted(QUALIFICATION_EVIDENCE_TYPES))
    parser.add_argument("metadata", type=Path, help="UTF-8 JSON qualification result")
    parser.add_argument("--target", required=True, help="real qualification target identifier")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--executed-at", default=None, help="ISO-8601 execution timestamp")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "docs/release/evidence/manifest.json",
    )
    args = parser.parse_args()
    try:
        path = generate_report(
            args.evidence_type,
            args.metadata,
            args.target,
            args.output,
            args.manifest,
            executed_at=args.executed_at,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(path)


if __name__ == "__main__":
    main()
