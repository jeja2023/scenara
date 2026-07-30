# Scenara implementation and acceptance matrix

This matrix is the repository-level checklist for `Scenara 景枢全面优化升级方案.md`.
`complete` requires implementation plus the evidence named in the last column.
Items that require licensed model assets or target hardware remain incomplete
until signed, reproducible evidence is committed.

Current development version: `0.3.0-dev.0` (`0.3.0.dev0` for Python packages).
This version is an engineering qualification snapshot, not a `1.0.0` production release.

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
| 0.9 | Versioned repository topology for the platform integration repository, existing Model training repository and gated future Data repository; immutable manifests, APIs/events and hard repository boundaries | complete | topology API tests, OpenAPI and SDK drift checks, Chinese Console ownership view and cross-repository contract documentation |
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
- [ ] The exact software `LICENSE` text has legal approval for commercial distribution and a signed report bound to its SHA-256.
- [ ] Signed offline installation and backup/restore evidence exists (the local
  PostgreSQL + MinIO recovery drill passes).

The `1.0` version must not be published while any box above is unchecked.

## Current local verification

The following checks were executed on 2026-07-30 and are supporting implementation evidence only:

| Check | Result |
|---|---|
| `python -m pytest -q --cov=scenara --cov=sdk/python/scenara_sdk --cov-fail-under=75` | 88 passed, 6 integration tests skipped by default; 78.56% coverage |
| `SCENARA_RUN_INTEGRATION=1 python -m pytest -q -m integration tests/integration` | 6 passed against Docker PostgreSQL/pgvector, Redis and MinIO, including IAM persistence and API key lifecycle |
| `scripts/local_backup_restore_drill.ps1` | passed; PostgreSQL and MinIO markers restored and verified |
| `npm run check` | passed; console lint, 6 console tests, typecheck, build and TypeScript SDK check |
| `pnpm run console:e2e` | 30 passed across desktop Chrome and Pixel 7 viewports; all 12 routes checked for page errors and horizontal overflow, including the product matrix, repository topology and IAM management workspace |
| Ruff (including `app/` correctness rules), Mypy, OpenAPI/SDK drift, repository gate, implementation release gate | all passed |
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
