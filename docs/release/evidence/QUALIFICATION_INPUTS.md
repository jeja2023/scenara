# Qualification Input Contracts

The qualification generator creates a candidate passed report only when the
referenced raw files prove every required condition. It does not update the
release manifest. Relative paths are resolved from the directory containing
the top-level input JSON. Every top-level input uses schema version 1.0 and an
evidence type matching the command.

Generate a candidate, inspect it, and then record it:

    python scripts/prepare_release_evidence.py gpu_capacity /secure/gpu-input.json \
      --target "Ubuntu 24.04 capacity host" \
      --output /secure/gpu-capacity-report.json

    python scripts/record_release_evidence.py /secure/gpu-capacity-report.json

The first command leaves the manifest unchanged. The second command changes
only the matching pending entry. Both commands refuse to overwrite completed
evidence or an existing output file.

## Evaluation Input

Use portrait_evaluation or ocr_evaluation. The dataset manifest contains a
non-empty dataset_version and rights_cleared set to true. The threshold file
contains fixed_at, thresholds, and tolerances. Threshold keys end in _min or
_max; tolerances cover exactly the same metrics. The fixed_at timestamp must
predate both independent run timestamps.

Top-level input:

    {
      "schema_version": "1.0",
      "evidence_type": "portrait_evaluation",
      "dataset_manifest_path": "portrait-dataset.json",
      "thresholds_path": "portrait-thresholds.json",
      "command": "python evaluate_portrait.py --dataset portrait-1.0.0",
      "runs": [
        {"output_path": "portrait-run-a.json"},
        {"output_path": "portrait-run-b.json"}
      ]
    }

Threshold file:

    {
      "fixed_at": "2026-08-12T01:00:00Z",
      "thresholds": {"map_min": 0.80},
      "tolerances": {"map": 0.01}
    }

Each run output:

    {
      "run_id": "portrait-run-a",
      "executed_at": "2026-08-13T01:00:00Z",
      "exit_code": 0,
      "metrics": {"map": 0.91}
    }

The generator hashes the dataset manifest, threshold file, and run outputs. It
independently evaluates every threshold and the cross-run tolerance.

## GPU Capacity Input

GPU memory is a measured descriptive value. There is no 24 GB lower bound and
no upper bound. Qualification depends on finite measurements, peak VRAM fitting
the measured device, and five successful scenario outputs.

    {
      "schema_version": "1.0",
      "evidence_type": "gpu_capacity",
      "device": {"name": "NVIDIA target device", "driver_version": "575.57"},
      "measurement": {
        "gpu_memory_mib": 8192,
        "p50_ms": 10,
        "p95_ms": 20,
        "p99_ms": 30,
        "throughput_per_second": 4,
        "error_rate": 0,
        "peak_vram_mib": 7000,
        "duration_seconds": 3600,
        "command": "python capacity.py --duration 3600",
        "scenarios": [
          "sustained_load", "burst", "vram_pressure", "backpressure", "recovery"
        ],
        "scenario_results": {
          "sustained_load": {"output_path": "sustained-load.json"},
          "burst": {"output_path": "burst.json"},
          "vram_pressure": {"output_path": "vram-pressure.json"},
          "backpressure": {"output_path": "backpressure.json"},
          "recovery": {"output_path": "recovery.json"}
        }
      }
    }

Each scenario output identifies itself and has a zero exit code, for example:

    {"scenario": "burst", "exit_code": 0}

All five files must be unique. Their SHA-256 values and the top-level raw input
digest are computed by the generator.

## Model Rights Input

The input points to every real model artifact and rights-record JSON:

    {
      "schema_version": "1.0",
      "evidence_type": "model_rights",
      "models": [
        {
          "artifact_path": "portrait-detector.bin",
          "rights_record_path": "portrait-detector-rights.json"
        }
      ]
    }

Each rights record also uses schema version 1.0 and evidence type model_rights.
It contains model_id, model_version, artifact_sha256, license_identifier,
license_source_uri, source_uri, and these four true flags:
intended_use_allowed, redistribution_allowed, rights_cleared, and
source_identity_verified. The declared digest must match the artifact computed
by the generator. The rights record itself is also hashed.

## Offline Installation Input

On the isolated blank Ubuntu 24.04 host, ask the installer to write its atomic
structured result as the third argument:

    deploy/scripts/install-offline.sh \
      /srv/scenara-offline-0.3.0-dev.21 \
      /secure/scenara.env \
      /secure/offline-installer-result.json

Run the example clients and core Parse smoke check separately. Each produces a
unique JSON output with its check identity and zero exit code, for example:

    {"check": "core_parse", "exit_code": 0}

Then provide:

    {
      "schema_version": "1.0",
      "evidence_type": "offline_install",
      "blank_host": true,
      "isolated_network": true,
      "bundle_path": "scenara-offline-0.3.0-dev.21.tar.gz",
      "installer_result_path": "offline-installer-result.json",
      "source_commit_path": "source-commit.txt",
      "check_results": {
        "example_clients": {"output_path": "example-clients.json"},
        "core_parse": {"output_path": "core-parse.json"}
      }
    }

The installer result supplies the verified host, measured GPU memory, checksum
state, health and console checks, and all seven required service states. The
generator hashes the installer result, bundle, and external smoke outputs.
