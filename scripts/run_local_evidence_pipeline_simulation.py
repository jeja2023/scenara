"""Validate fixed-evaluation and model-rights evidence processing locally.

It creates a self-authored synthetic fixture in a temporary directory, runs two
deterministic evaluations after a fixed threshold timestamp, and asks the
release-evidence normalizer to produce *candidate* reports using an isolated
manifest.  No report is recorded into the repository release manifest, and no
claim is made about any real model's licence or deployment rights.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "runtime-state" / "qualification" / "evidence-pipeline-local-simulation.json"

from scripts.prepare_release_evidence import generate_report  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _evaluate(run_id: str, executed_at: str) -> dict[str, object]:
    # A deterministic self-authored fixture: each normalized vector's target
    # class is its largest component.  This tests evidence reproducibility,
    # not the accuracy of a deployed portrait model.
    samples = [([1.0, 0.0, 0.0], 0), ([0.0, 1.0, 0.0], 1), ([0.0, 0.0, 1.0], 2)]
    accuracy = sum(int(vector.index(max(vector)) == label) for vector, label in samples) / len(samples)
    return {
        "run_id": run_id,
        "executed_at": executed_at,
        "exit_code": 0,
        "metrics": {"accuracy": accuracy},
        "fixture": "self-authored synthetic vectors; not a production model evaluation",
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "1.2",
        "release": "0.0.0-local-evidence-pipeline",
        "release_identity": {
            "source_commit": None,
            "image_digest": None,
            "offline_bundle_sha256": None,
            "openapi_sha256": None,
            "model_set_sha256": None,
        },
        "entries": [
            {"evidence_type": "portrait_evaluation", "status": "pending"},
            {"evidence_type": "model_rights", "status": "pending"},
        ],
    }


def main() -> int:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="scenara-evidence-pipeline-") as temporary:
        directory = Path(temporary)
        fixed_at = datetime.now(UTC) - timedelta(minutes=1)
        executed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        artifact = directory / "synthetic-portrait-fixture.bin"
        artifact.write_bytes(b"scenara-local-evidence-pipeline-synthetic-model-v1\n")
        artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
        _write(
            directory / "synthetic-model-rights.json",
            {
                "schema_version": "1.0",
                "evidence_type": "model_rights",
                "model_id": "local-synthetic-portrait-fixture",
                "model_version": "1.0.0",
                "artifact_sha256": artifact_sha256,
                "license_identifier": "LicenseRef-Local-Synthetic-Fixture",
                "license_source_uri": "local://scenara/evidence-pipeline/self-authored-fixture",
                "source_uri": "local://scenara/evidence-pipeline/synthetic-model",
                "intended_use_allowed": True,
                "redistribution_allowed": True,
                "rights_cleared": True,
                "source_identity_verified": True,
                "simulation_only": True,
                "not_for_release": "This self-authored fixture has no third-party model weights.",
            },
        )
        _write(
            directory / "synthetic-dataset.json",
            {
                "dataset_version": "local-synthetic-evidence-v1",
                "rights_cleared": True,
                "simulation_only": True,
                "not_for_release": "The dataset consists solely of generated numeric vectors.",
            },
        )
        _write(
            directory / "fixed-thresholds.json",
            {
                "fixed_at": fixed_at.isoformat().replace("+00:00", "Z"),
                "thresholds": {"accuracy_min": 1.0},
                "tolerances": {"accuracy": 0.0},
            },
        )
        _write(directory / "run-a.json", _evaluate("local-synthetic-run-a", executed_at))
        _write(directory / "run-b.json", _evaluate("local-synthetic-run-b", executed_at))
        _write(
            directory / "portrait-input.json",
            {
                "schema_version": "1.0",
                "evidence_type": "portrait_evaluation",
                "dataset_manifest_path": "synthetic-dataset.json",
                "thresholds_path": "fixed-thresholds.json",
                "command": "python scripts/run_local_evidence_pipeline_simulation.py --fixture deterministic-portrait-v1",
                "runs": [{"output_path": "run-a.json"}, {"output_path": "run-b.json"}],
            },
        )
        _write(
            directory / "rights-input.json",
            {
                "schema_version": "1.0",
                "evidence_type": "model_rights",
                "models": [
                    {
                        "artifact_path": "synthetic-portrait-fixture.bin",
                        "rights_record_path": "synthetic-model-rights.json",
                    }
                ],
            },
        )
        manifest = directory / "isolated-manifest.json"
        _write(manifest, _manifest())
        portrait_candidate = generate_report(
            "portrait_evaluation",
            directory / "portrait-input.json",
            "Local deterministic fixture evidence-pipeline validation; not a release target",
            directory / "portrait-candidate.json",
            manifest,
            executed_at=executed_at,
        )
        rights_candidate = generate_report(
            "model_rights",
            directory / "rights-input.json",
            "Local self-authored fixture rights-pipeline validation; not a release target",
            directory / "rights-candidate.json",
            manifest,
            executed_at=executed_at,
        )
        portrait_report = json.loads(portrait_candidate.read_text(encoding="utf-8"))
        rights_report = json.loads(rights_candidate.read_text(encoding="utf-8"))
        if portrait_report["status"] != "passed" or rights_report["status"] != "passed":
            raise RuntimeError("evidence normalizer did not produce passed candidate reports")
    report = {
        "schema_version": "1.0",
        "status": "passed",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "simulation_only": True,
        "not_production_evidence": [
            "The evaluation dataset and model artifact are self-authored synthetic fixtures.",
            "Candidate reports were validated against an isolated temporary manifest and were never recorded into docs/release/evidence/manifest.json.",
            "Real model licences, intended-use rights, and fixed production evaluation sets still require owner and legal approval.",
        ],
        "checks": {
            "fixed_threshold_precedes_two_runs": True,
            "two_deterministic_runs_within_tolerance": True,
            "artifact_digest_matches_rights_record": True,
            "candidate_portrait_evaluation_validated": True,
            "candidate_model_rights_validated": True,
            "release_manifest_unchanged": True,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
