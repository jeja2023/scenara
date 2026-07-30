# Scenara 1.0 release evidence

This directory is intentionally fail-closed. The release manifest is a release artifact, not a planning document. Do not create it until every referenced report exists, has a verified SHA-256, records the execution target, and has named approval.

Implementation gate:

    python scripts/release_gate.py --implementation-only

Strict 1.0 gate:

    python scripts/release_gate.py

The strict gate requires exactly one entry for every evidence type listed in manifest.example.json. Every report must be UTF-8 JSON under `docs/release/evidence/reports/`, use `schema_version: "1.0"`, and repeat the entry's evidence type, status, timestamps, signer, target, and metadata. The manifest stores the report's verified SHA-256.

Evaluation reports must identify a fixed, versioned, legally cleared dataset, pre-approved thresholds, and two independent runs within tolerance. Capacity evidence must come from the supported Ubuntu x86_64 target with exactly one 24 GB NVIDIA GPU and include latency percentiles, throughput, error rate, peak VRAM, sustained load, burst, pressure, backpressure, and recovery. Integration, security, model-rights, offline-install, and backup reports must include the required scenario metadata shown in the example manifest. A template, placeholder signer, skipped test, development-machine substitution, or unsigned report is not evidence.
