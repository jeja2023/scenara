# Scenara implementation and acceptance matrix

This matrix is the repository-level checklist for `Scenara 景枢全面优化升级方案.md`.
`complete` requires implementation plus the evidence named in the last column.
Items that require licensed model assets or target hardware remain incomplete
until signed, reproducible evidence is committed.

| Stage | Deliverable | Status | Evidence required |
|---|---|---|---|
| 0.1 | Brand, license, provenance, boundaries, ADR, OpenAPI, migration, CI, production Compose | complete | repository, contract, and Compose configuration gates |
| 0.2 | Portrait and OCR vertical Media/Run/Operator/Pipeline/Result paths | complete | deterministic domain contract tests |
| 0.3 | Image, video, PDF, stream, scheduling, checkpoint, SSE, webhook, feature store, retention, result shards | locally qualified; release sign-off pending | local Docker integration suite passes; signed real-service integration report required |
| 0.4 | Detection, ReID, face, pose, parsing, apparel, segmentation, gait, quality fusion | implemented; model qualification pending | licensed model packages and fixed Portrait evaluation report required |
| 0.5 | OCR detection/recognition, reading order, title, paragraph, image, table layout | implemented; model qualification pending | fixed Chinese/rotated/PDF/layout evaluation report required |
| 0.6 | License, entitlements, quota, metering, SLA, incident, support, compliance evidence via policy provider | complete | signed-license, fail-closed quota, incident, support, and evidence tests |
| 0.7 | Overview, media, runs, results, Portrait, OCR, pipeline, models, access, operations, enterprise and feedback console; Python and generated TS SDKs | complete | 12-route desktop/mobile browser checks, frontend tests, static `/console/` delivery, SDK and OpenAPI drift tests |
| 1.0 | Ubuntu Compose, 24 GB NVIDIA, PostgreSQL/pgvector, Redis, MinIO, offline install, backup/restore | implementation and local recovery drill complete; target qualification pending | strict release gate requires capacity, offline, and signed recovery reports |
| 1.1 | Feedback review, verified Run/Result provenance, compliant hard-sample manifests, governed model lifecycle, deployment events, and rollback | complete | feedback authorization, caller-reference rejection, tenant isolation, state-machine, SDK, console, and PostgreSQL tests |
| 2.0 | Trigger-based new Domain expansion | not started; intentionally gated | two validated customer scenarios, legal model/data, owner and operations budget |

## Release gates

- [x] Source capability matrix marks each imported capability migrated,
  reimplemented, or explicitly retired.
- [x] Architecture and public contract suites pass.
- [ ] Signed PostgreSQL/pgvector, Redis, and MinIO qualification report exists (the local Docker suite passes; local output is not a release signature).
- [x] SSRF, malicious image/PDF, decompression bomb, authorization, credential
  redaction, embedding authorization, audit fail-closed, and biometric deletion
  tests pass.
- [ ] Versioned and legally cleared Portrait and OCR evaluation manifests and
  signed reports exist.
- [ ] 24 GB GPU sustained load, burst, VRAM pressure, backpressure, and recovery
  reports exist from the supported target.
- [x] Repository gates cover secret patterns, model asset policy, proprietary
  license, provenance, security policy, and legacy brand identifiers. CI also
  generates dependency license inventories and an SBOM.
- [ ] Signed offline installation and backup/restore evidence exists (the local
  PostgreSQL + MinIO recovery drill passes).

The `1.0` version must not be published while any box above is unchecked.

## Current local verification

The following checks were executed on 2026-07-30 and are supporting implementation evidence only:

| Check | Result |
|---|---|
| `python -m pytest -q` | 62 passed, 5 integration tests skipped by default; each skip requires `SCENARA_RUN_INTEGRATION=1` |
| `SCENARA_RUN_INTEGRATION=1 python -m pytest -q -m integration tests/integration` | 5 passed against Docker PostgreSQL/pgvector, Redis and MinIO |
| `scripts/local_backup_restore_drill.ps1` | passed; PostgreSQL and MinIO markers restored and verified |
| `npm run check` | passed; console lint, 6 console tests, typecheck, build and TypeScript SDK check |
| Ruff, Mypy, OpenAPI/SDK drift, repository gate, implementation release gate | all passed |
| `python -m pip_audit -r requirements/dev.txt` and `pnpm audit --audit-level high` | no known vulnerabilities in the committed dependency definitions |
| Deployment script syntax | all `deploy/scripts/*.sh` files passed `bash -n` in a cached Linux container |
| Strict `python scripts/release_gate.py` | intentionally failed closed because `docs/release/evidence/manifest.json` and signed reports are not present |

Local results do not satisfy the target GPU, licensed model, fixed evaluation-set, offline-install or named approval requirements. Those items remain unchecked until the responsible owners produce reproducible signed evidence.
