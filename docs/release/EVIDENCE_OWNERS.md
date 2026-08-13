# Release Evidence Responsibilities

Scenara is currently a personal development project. The evidence contract therefore records the person who performs a check only through the report's execution target and reproducible output. It does not require a named approver, an approval timestamp, a legal approver, or a controlled approval record number.

| Evidence type | Project-owner check | Required objective coverage |
|---|---|---|
| `integration_services` | Run the integration suite | PostgreSQL/pgvector, Redis, MinIO, no skipped tests, no duplicate logical results, Redis rebuild |
| `security_assessment` | Run the security test suite | SSRF, malicious media, authorization, credential redaction, audit fail-closed, biometric deletion |
| `model_rights` | Record the model inventory and rights state | Every model has a version, artifact SHA-256, license identifier, source URI, and cleared-rights flag |
| `software_license` | Hash, identify, and self-review the repository `LICENSE` | Exact `LICENSE` SHA-256, SPDX identifier, and terms-completeness review scope; no external legal approval claim |
| `portrait_evaluation` | Run the fixed portrait evaluation | Versioned rights-cleared dataset, fixed thresholds, two runs within tolerance |
| `ocr_evaluation` | Run the fixed OCR evaluation | Versioned rights-cleared dataset, fixed thresholds, two runs within tolerance |
| `gpu_capacity` | Run the capacity workload on the target GPU | Sustained load, burst, VRAM pressure, backpressure, recovery, latency and throughput metrics |
| `offline_install` | Install on an isolated blank host | Checksums, health, console, example clients, core parse |
| `backup_restore` | Run the recovery drill | RPO/RTO and verification of all required business entities |

Each evidence type appears exactly once in `docs/release/evidence/manifest.json`. Use `pending` when the check has not been performed. A `passed` entry must include its report path, report SHA-256, execution time, target, release identity, and type-specific metadata. The release gate remains fail-closed while any required evidence is pending.
