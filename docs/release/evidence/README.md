# Scenara 1.0 release evidence

This directory is intentionally fail-closed. The release manifest is a release artifact, not a planning document. Do not create it until every referenced report exists, has a verified SHA-256, records the execution target, and has named approval.

Implementation gate:

    python scripts/release_gate.py --implementation-only

Strict 1.0 gate:

    python scripts/release_gate.py

The strict gate requires exactly one entry for every evidence type listed in manifest.example.json. Every report must be UTF-8 JSON under `docs/release/evidence/reports/`, use `schema_version: "1.0"`, and repeat the entry's evidence type, status, timestamps, signer, target, and metadata. The manifest stores the report's verified SHA-256.

Evaluation reports must identify a fixed, versioned, legally cleared dataset, pre-approved thresholds, and two independent runs within tolerance. Capacity evidence must come from the supported Ubuntu x86_64 target with exactly one 24 GB NVIDIA GPU and include latency percentiles, throughput, error rate, peak VRAM, sustained load, burst, pressure, backpressure, and recovery. Integration, security, model-rights, offline-install, and backup reports must include the required scenario metadata shown in the example manifest. A template, placeholder signer, skipped test, development-machine substitution, or report without named approval is not evidence.

The repository gate validates report integrity, consistency, and named approval; it does not establish the approver's identity cryptographically. Reports must enter this directory through the controlled release process after the responsible owner verifies the approval record. When an organization requires cryptographic attestation, its signing system must verify the report before import and retain the signature and trust-chain record outside this public repository.

## Model release qualification objects

The governed model lifecycle uses evidence objects in the configured object store. Each reference must use this exact form:

    tenants/<tenant>/projects/<project>/model-evidence/<name>.json#sha256=<64 lowercase hex characters>

The referenced UTF-8 JSON object uses `schema_version: "1.0"`, `status: "passed"`, and records `model_id`, `model_version`, `package_sha256`, timezone-aware `executed_at` and `approved_at` timestamps, a named non-placeholder `signed_by` approver, and type-specific `details`. The model id, version, package digest, object digest, tenant, and project must match the release request.

Every transition beyond `candidate` requires unique `model_rights`, domain evaluation (`portrait_evaluation` or `ocr_evaluation`), and `regression` objects. Rights evidence must set `rights_cleared: true`; evaluation evidence must record at least two independent runs, thresholds approved before execution, and results within tolerance; regression evidence must set `regressions_passed: true`. Missing, unreadable, duplicated, altered, mismatched, unsigned, or placeholder evidence fails closed.
