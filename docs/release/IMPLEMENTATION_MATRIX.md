# Scenara implementation and acceptance matrix

This matrix is the repository-level checklist for `Scenara 景枢全面优化升级方案.md`.
`complete` requires implementation plus the evidence named in the last column.
Items that require licensed model assets or target hardware remain incomplete
until signed, reproducible evidence is committed.

Current development version: `0.3.0-dev.5` (`0.3.0.dev5` for Python packages).
This version is an engineering qualification snapshot, not a `1.0.0` production release.

The `0.3.0-dev.5` engineering baseline additionally fixes the migration and
capacity evidence boundary: `app/` contains 43 reachable Python modules (about
6,882 lines), list pagination/count/existence checks execute in the state
backend, published contract bytes are LF-stable, and CI measures coverage over
`scenara`, `app`, and the Python SDK together. Video and live-stream person
detection now consumes progressive decoded batches, persists monotonic Run
progress, and exposes replaceable partial Result snapshots before completion.

| Stage | Deliverable | Status | Evidence required |
|---|---|---|---|
| 0.1 | Brand, license, provenance, boundaries, ADR, OpenAPI, migration, CI, production Compose | engineering complete; legal license approval pending | repository, contract, Compose gates, and signed software-license approval |
| 0.2 | Portrait and OCR vertical Media/Run/Operator/Pipeline/Result paths | complete | deterministic domain contract tests |
| 0.3 | Image, video, PDF, stream, scheduling, checkpoint, SSE, webhook, feature store, retention, result shards | locally qualified; release sign-off pending | local Docker integration suite passes; signed real-service integration report required |
| 0.4 | Detection, ReID, face, pose, parsing, apparel, segmentation, gait, quality fusion | implemented; model qualification pending | licensed model packages and fixed Portrait evaluation report required |
| 0.5 | OCR detection/recognition, reading order, title, paragraph, image, table layout | implemented; model qualification pending | fixed Chinese/rotated/PDF/layout evaluation report required |
| 0.6 | License, entitlements, quota, metering, SLA, incident, support, compliance evidence via policy provider | complete | signed-license, fail-closed quota, incident, support, and evidence tests |
| 0.7 | Overview, product catalog, media, runs, results, Portrait, OCR, pipeline, models, access, operations, enterprise and feedback console; Chinese-first UI contract; Python and generated TS SDKs | complete | 12-route desktop/mobile browser checks, visible-English leakage scan, frontend tests, static `/console/` delivery, SDK and OpenAPI drift tests |
| 0.8 | Product matrix and shared IAM foundation: organizations, projects, users, roles, memberships, service accounts, API keys, product entitlements and product-aware authorization | engineering complete; federation and commercial lifecycle gated | API/service tests, PostgreSQL migration and integration tests, one-time secret handling, scope narrowing, entitlement suspension, tenant isolation, Console and SDK contract checks |
| 0.9 | Versioned repository topology plus four published cross-repository contracts for the platform integration repository, existing Model training repository and gated future Data repository | complete | topology/catalog API tests, Draft 2020-12 schemas and examples, SHA-256 release lock, deterministic CI bundle, provider validation and backward-compatibility tests |
| 1.0 | Ubuntu Compose, 24 GB NVIDIA, PostgreSQL/pgvector, Redis, MinIO, offline install, backup/restore | implementation and local recovery drill complete; target qualification pending | strict release gate requires capacity, offline, and signed recovery reports |
| 1.1 | Feedback review, verified Run/Result provenance, compliant hard-sample manifests, formal model admission, governed lifecycle, per-capability runtime switching, deployment-feedback outbox, and rollback | complete | immutable admission, evidence/state-machine, Run binding freeze, exact legacy-runtime selection, signed webhook delivery, SDK, console, PostgreSQL and compatibility tests |
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
- [ ] The exact software `LICENSE` text has legal approval for commercial distribution and a signed report bound to its SHA-256.
- [ ] Signed offline installation and backup/restore evidence exists (the local
  PostgreSQL + MinIO recovery drill passes).

The `1.0` version must not be published while any box above is unchecked.

## Current local verification

The following checks were executed on 2026-08-03 and are supporting implementation evidence only:

| Check | Result |
|---|---|
| `python -m pytest -q --cov=scenara --cov=app --cov=sdk/python/scenara_sdk --cov-fail-under=60` | 153 passed, 8 integration tests skipped by default; 63.05% coverage across 11,647 statements |
| Real GOP keyframe cross-check | PyAV and Scenara both selected frames `0, 12, 24, 36, 48, 60, 72, 84, 96, 108`; normal decode no longer uses the FFmpeg raw-only keyframe flag |
| Real-time video and stream browser qualification | HEVC file Run `run_915a658dcd69469a81877c21ee2f22ab` exposed 8/16/24-unit partial results before completing 32 units with 21 objects; HTTP MPEG-TS Run `run_2e3c39dd7f6b4c4aa65f27b3820a277c` exposed units 1-8 individually and completed with 7 objects; after an API container force-recreate, persisted Source `src_1cd455c67c7548cdad6aa9f35f1ed63a` successfully previewed and Run `run_9816db5634ec4b13a057e36566901224` exposed 4/8 units before completing with 9 objects; crop JPEGs, 1920x1080 full frames, highlights, and Results-page replay loaded successfully |
| `SCENARA_RUN_INTEGRATION=1 python -m pytest -q -m integration tests/integration` | 8 tests collected for PostgreSQL/pgvector, Redis and MinIO; the dev.4 pagination and artifact additions require the CI real-service job or a local Compose qualification run |
| `scripts/local_backup_restore_drill.ps1` | passed; PostgreSQL and MinIO markers restored and verified |
| `pnpm run check` | passed; Prettier, warning-free console lint, 17 console tests, typecheck, build and TypeScript SDK runtime/contract check |
| `pnpm run console:e2e` | 34 passed across desktop Chrome and Pixel 7 viewports; all 12 routes plus complete image/video/PDF/stream controls and cancellation tracking checked for page errors and horizontal overflow |
| Ruff (including `app/` correctness rules), Mypy, OpenAPI/SDK drift, published repository-contract drift/compatibility, repository gate, implementation release gate | all passed |
| `python -m pip_audit -r requirements/dev.txt` and `pnpm audit --audit-level high` | no known vulnerabilities in the committed dependency definitions |
| Deployment script syntax | all `deploy/scripts/*.sh` files passed `bash -n` in a cached Linux container |
| Strict `python scripts/release_gate.py` | intentionally failed closed because the software license is not legally approved and the nine signed reports are not present |

Local results do not satisfy software-license legal approval, the target GPU, licensed model, fixed evaluation-set, offline-install, or named approval requirements. Those items remain unchecked until the responsible owners produce reproducible signed evidence.

## Product matrix gates after 0.3.0

- Interactive user sessions, OIDC, SAML, SCIM and login-time Membership/Role resolution remain gated.
- Quotas, plans, seats, metering, billing, self-service purchase and full commercial entitlement lifecycle remain gated.
- User, project and service-account disable/delete/restore approvals plus centralized audit search/export/retention remain gated.
- Model training and experiment tracking, full Data governance, Edge device management, generic Index resources, Search, Flow and Agent are not production-complete.
- These capabilities must extend the shared IAM and product catalog instead of introducing per-product identity, authorization or deployment stacks.
- The current repository remains the platform integration repository. Model training stays in its existing professional repository; Data is split only after first-class dataset ownership and versioned handoff contracts are stable.
