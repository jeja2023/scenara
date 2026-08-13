# Scenara Release Evidence

This directory records objective release evidence for the personal Scenara project. It does not require named approvers, approval timestamps, legal approvers, or controlled approval record numbers.

Implementation gate:

    python scripts/release_gate.py --implementation-only

Strict release gate:

    python scripts/release_gate.py

Record a completed report after a real qualification run:

    python scripts/record_release_evidence.py /secure/result.json

Generate a candidate directly from a raw qualification result (the command
normalizes only objective facts and refuses to write output unless the same
`validate_entry` contract passes):

    python scripts/prepare_release_evidence.py gpu_capacity /secure/gpu-result.json \
      --target 'Ubuntu 24.04 qualification host with measured NVIDIA device' \
      --output /secure/gpu-capacity-report.json

The exact input contracts and end-to-end commands for evaluation, GPU capacity,
model rights, and offline installation are in
[QUALIFICATION_INPUTS.md](QUALIFICATION_INPUTS.md).

Every top-level qualification input uses schema version 1.0 and an evidence
type matching the command. Relative paths are resolved against that input file.
The generator reads the referenced files itself and computes their SHA-256
values; caller-supplied digests are not accepted as substitutes. Reports are
never synthesized from missing or estimated values, and existing output is
never overwritten.

The recorder accepts only `schema_version: "1.0"`, `status: "passed"` reports whose release identity matches the manifest. It validates the objective metadata, writes the canonical report atomically, computes its SHA-256, and replaces the matching pending entry. It does not create evidence or turn an incomplete result into a pass.

The strict gate requires manifest `schema_version: "1.2"` and exactly one entry for every evidence type listed in `manifest.example.json`. Entries may be `pending` while the project is under development. A pending entry contains only `evidence_type` and `status`; it must not claim a report, digest, execution time, or metadata. The strict gate fails closed until every entry is `passed`.

Each passed report must be UTF-8 JSON under `docs/release/evidence/reports/`, use report `schema_version: "1.0"`, and repeat the manifest entry's evidence type, status, execution time, target, release identity, and metadata. The manifest stores the report's verified SHA-256. Reports must use a real execution target and exact, reproducible metadata; placeholders and skipped checks are not evidence.

The release identity binds completed evidence to one full Git commit, application image digest, offline-bundle SHA-256, OpenAPI SHA-256, and model-set SHA-256. During personal-project development these values may be `null` while any evidence remains pending. A completed release must populate every identity value, match the checked-out commit, and match the repository OpenAPI digest.

Evaluation reports must identify a fixed, versioned, rights-cleared dataset, thresholds fixed before execution, and two independent runs within tolerance. Capacity evidence must come from the supported target and include latency percentiles, throughput, error rate, peak VRAM, sustained load, burst, pressure, backpressure, and recovery. Model-rights evidence must record each production model's id, version, artifact SHA-256, license identifier, source URI, and cleared-rights flag. Integration, security, model-rights, software-license, offline-install, and backup reports must include the required objective metadata shown in the example manifest.

Software-license evidence binds the exact `LICENSE` SHA-256 and SPDX identifier and records the sections covered by the personal-project license self-review. This is a terms-completeness check, not external legal advice; it does not claim company legal approval or a controlled approval record.

## Model release qualification objects

The governed model lifecycle uses evidence objects in the configured object store. Each reference must use this exact form:

    tenants/<tenant>/projects/<project>/model-evidence/<name>.json#sha256=<64 lowercase hex characters>

The referenced UTF-8 JSON object uses `schema_version: "1.0"`, `status: "passed"`, and records `model_id`, `model_version`, `package_sha256`, timezone-aware `executed_at`, and type-specific `details`. Named approver fields are not part of the personal-project release evidence contract. The model id, version, package digest, object digest, tenant, and project must match the release request.

Every transition beyond `candidate` requires unique `model_rights`, domain evaluation (`portrait_evaluation` or `ocr_evaluation`), and `regression` objects. Rights evidence must set `rights_cleared: true`; evaluation evidence must record at least two independent runs, thresholds fixed before execution, and results within tolerance; regression evidence must set `regressions_passed: true`. Missing, unreadable, duplicated, altered, mismatched, or placeholder evidence fails closed.
