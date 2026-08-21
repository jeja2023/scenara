# Scenara implementation and acceptance matrix

This matrix is the repository-level checklist for `Scenara 景枢全面优化升级方案.md`.
`complete` requires implementation plus the evidence named in the last column.
Items that require licensed model assets or target hardware remain incomplete
until reproducible objective evidence is committed.

Current development version: `0.3.0-dev.25` (`0.3.0.dev25` for Python packages).

## Release Gate Status
The `0.3.0-dev.25` engineering baseline adds a provider-neutral Qdrant `FeatureStore` adapter with tenant/project filters, deterministic feature-space metadata, expiry filtering, and contract tests on top of the previous contract and observability hardening. The previous performance, reliability, Console and deployment convergence work remains part of the current baseline. The repository is MIT-licensed, and the default Compose profile is personal mode; signed enterprise policy remains an opt-in extension.
Formal 1.0 release evidence remains fail-closed until the required evaluation,
GPU capacity, offline-install, and model-rights checks are supplied for
`0.3.0-dev.25`. Existing integration, security, backup/restore, and software-license
reports are digest-bound to the current OpenAPI contract; historical `0.3.0-dev.21`
reports remain archived and are not reused as current-release evidence. This personal
project does not require named approvers or legal/commercial sign-off records.

## Implementation Parity Matrix
The `0.3.0-dev.25` baseline processes finite video and PDF inputs to EOF unless callers
explicitly request a compatibility cap. Continuous streams are archived into linked Run
segments under one Stream Session, while inference batches publish `result.delta` events
and append-only Result shards. Production uses the local personal policy by default; the signed enterprise policy
provider remains available through the opt-in Compose extension. The baseline also adds indexed and expiring Session
authentication, paginated/streaming audit access, bulk Result reads, SSE
fallback control, Console auth-expiry handling, composable/router extraction,
and `runtime-state/logs/` governance. Portrait video and stream results omit
zero-object units while retaining analyzed sample counts and original hit
timestamps; normal finite-media EOF is reported as successful source completion.
It also completes the cross-video pedestrian Re-ID loop: in-video tracklets,
long-term identity registration across Runs and cameras, camera topology and
transition constraints, adjudication actions, public identity queries, and
real two-video end-to-end coverage. Dataset, Version and Annotation requests now enter through Core's stable public API and are delegated to the configured Data platform client; the local adapter remains limited to development and migration verification.

| Stage | Deliverable | Status | Evidence required |
|---|---|---|---|
| 0.1 | Brand, license, provenance, boundaries, ADR, OpenAPI, migration, CI, production Compose | engineering complete; license self-check recorded | repository, contract, Compose gates, and exact software-license hash |
| 0.2 | Portrait and OCR vertical Media/Run/Operator/Pipeline/Result paths | complete | deterministic domain contract tests |
| 0.3 | Image, video, PDF, stream, scheduling, checkpoint, SSE, webhook, feature store, retention, result shards | qualified on isolated local services | reproducible PostgreSQL/pgvector, Redis, and MinIO integration report recorded |
| 0.4 | Detection, ReID, face, pose, parsing, apparel, segmentation, gait, quality fusion | implemented; model qualification pending | licensed model packages and fixed Portrait evaluation report required |
| 0.4a | In-video tracklets plus cross-camera long-term trajectory: multi-modal fusion, camera topology and mutual-exclusion constraints, real media timeline, capped template galleries, human adjudication, and cross-video identity persistence | implemented; model qualification pending | trajectory domain tests, PostgreSQL migration, camera-registry API, console adjudication route, SDK and OpenAPI drift checks, and real two-video E2E coverage |
| 0.5 | OCR detection/recognition, reading order, title, paragraph, image, table layout | implemented; model qualification pending | fixed Chinese/rotated/PDF/layout evaluation report required |
| 0.6 | License, entitlements, quota, metering, SLA, incident, support, compliance evidence via policy provider | complete | signed-license, fail-closed quota, incident, support, and evidence tests |
| 0.7 | Overview, product catalog, media, runs, results, Portrait, OCR, pipeline, models, access, operations, enterprise and feedback console; Chinese-first UI contract; Python and generated TS SDKs | complete | 12-route desktop/mobile browser checks, visible-English leakage scan, frontend tests, static `/console/` delivery, SDK and OpenAPI drift tests |
| 0.8 | Product matrix and shared IAM foundation: organizations, projects, users, roles, memberships, service accounts, API keys, product-aware authorization, lifecycle controls, identity-provider configuration/probes, sessions, quotas, audit retention, local metering and seat limits | development complete; external federation and payment settlement remain deployment-gated | API/service tests, PostgreSQL migrations, lifecycle approval tests, one-time secret handling, scope narrowing, quota fail-closed tests, tenant isolation, Console and SDK contract checks |
| 0.9 | Versioned repository topology plus four published cross-repository contracts, Core-to-Data remote client, checksummed migration export and cutover procedure | standalone Data development service, Core integration and local contract tests complete; production deployment/import/backup/recovery evidence remains gated | topology/catalog API tests, Data client compatibility/identity/idempotency tests, migration checksums, Draft 2020-12 schemas and examples, SHA-256 release lock, deterministic CI bundle, provider validation and backward-compatibility tests |
| 1.0 | Ubuntu Compose, NVIDIA capacity qualification, PostgreSQL/pgvector, Redis, MinIO, offline install, backup/restore | implementation and local recovery drill complete; target qualification pending | strict release gate requires measured capacity, offline, and reproducible recovery reports |
| 1.1 | Feedback review, verified Run/Result provenance, compliant hard-sample manifests, formal model admission, governed lifecycle, per-capability runtime switching, deployment-feedback outbox, and rollback | complete | immutable admission, evidence/state-machine, Run binding freeze, exact legacy-runtime selection, signed webhook delivery, SDK, console, PostgreSQL and compatibility tests |
| 2.0 | Trigger-based new Domain expansion plus shared Flow/Search/Edge/Agent control-plane foundations | development seed complete; production qualification intentionally gated | two validated customer scenarios, legal model/data, owner and operations budget |

## Release gates

- [x] Source capability matrix marks each imported capability migrated,
  reimplemented, or explicitly retired.
- [x] Architecture and public contract suites pass.
- [x] PostgreSQL/pgvector, Redis, and MinIO qualification report exists, including Redis pending-message recovery and full empty-stream rebuild from PostgreSQL/MinIO.
- [x] SSRF, malicious image/PDF, decompression bomb, authorization, credential
  redaction, embedding authorization, audit fail-closed, and biometric deletion
  tests pass.
- [ ] Versioned and rights-cleared Portrait and OCR evaluation manifests and
  reproducible reports exist.
- [ ] Measured GPU sustained load, burst, VRAM pressure, backpressure, and recovery
  reports exist from the supported target.
- [x] Repository gates cover secret patterns, model asset policy, MIT
  license, provenance, security policy, and legacy brand identifiers. CI also
  generates dependency license inventories and an SBOM.
- [x] The exact MIT `LICENSE` text and SPDX identifier are recorded in a
  self-check report bound to its SHA-256; no legal approval record is required.
- [x] PostgreSQL + MinIO backup/restore evidence exists and verifies tenants, projects, media, Runs, Results, Pipelines, Models, audit, and biometric records.
- [ ] Offline installation evidence exists from an isolated blank target host.

The `1.0` version must not be published while any box above is unchecked.

## Current local verification

The contract, observability, version and release-hardening regression was executed on 2026-08-20; the Core boundary, version synchronization and Console regression checks were executed on 2026-08-16; earlier release-evidence, browser and decode checks below remain supporting implementation evidence only:

| Check | Result |
|---|---|
| Full Python baseline for `0.3.0-dev.25` | 263 passed, 12 skipped; Ruff, Mypy, OpenAPI/SDK drift, repository contracts, and implementation/development gates pass |
| Security contract suite | 62 passed, 0 skipped; CI runs it once (the coverage job ignores the six security regression files, measured at 65.01% without them) |
| Console regression for `0.3.0-dev.25` | typecheck, production build and 24 unit tests passed; TypeScript SDK checks passed |
| Compose/Kubernetes tag convergence | `docker compose config` and `kubectl kustomize` resolve every application service to `scenara-api:${SCENARA_IMAGE_TAG:-0.3.0-dev.25}` |
| Core Data split regression | Core remote-client tests plus 3 standalone Data service/Core round-trip tests passed; production migration, import, backup/restore and cutover evidence remain gated |
| Console workspace regression | typecheck, 24 unit tests, production build and four-viewport Playwright checks passed; Data and Model routes expose distinct controlled theme accents without horizontal overflow |
| `.venv\\Scripts\\python.exe -m pytest -q` | 217 passed, 9 integration tests skipped in 57.55s; includes two-video trajectory ReID and `/api/v1/parse/video` shortcut coverage |
| Real GOP keyframe cross-check | PyAV and Scenara both selected frames `0, 12, 24, 36, 48, 60, 72, 84, 96, 108`; normal decode no longer uses the FFmpeg raw-only keyframe flag |
| Real-time video and stream browser qualification | HEVC file Run `run_915a658dcd69469a81877c21ee2f22ab` exposed 8/16/24-unit partial results before completing 32 units with 21 objects; HTTP MPEG-TS Run `run_2e3c39dd7f6b4c4aa65f27b3820a277c` exposed units 1-8 individually and completed with 7 objects; after an API container force-recreate, persisted Source `src_1cd455c67c7548cdad6aa9f35f1ed63a` successfully previewed and Run `run_9816db5634ec4b13a057e36566901224` exposed 4/8 units before completing with 9 objects; crop JPEGs, 1920x1080 full frames, highlights, and Results-page replay loaded successfully |
| `SCENARA_RUN_INTEGRATION=1 .venv\\Scripts\\python.exe -m pytest -q -m integration tests/integration -rs` | 12 passed, 0 skipped in 5.98s against isolated Docker-backed PostgreSQL/pgvector, Redis and MinIO; Redis rebuild, duplicate prevention and artifact persistence verified |
| Security contract suite | 61 passed, 0 skipped in 35.52s; SSRF, malicious media, authorization, credential redaction, audit fail-closed and biometric deletion covered |
| `scripts/local_backup_restore_drill.ps1` | passed; PostgreSQL and MinIO plus nine business-entity classes restored; RPO 3.967s and RTO 5.358s |
| `pnpm run check` plus Console lint/format checks | passed; 24 Console tests, typecheck, production build, warning-free ESLint, Prettier, and 2 TypeScript SDK contract tests |
| `npm run console:e2e` | 50 passed across desktop Chrome and mobile Chromium viewports; login, all workspaces, media controls, governance workflows, Chinese copy, ownership topology and horizontal overflow checked |
| Ruff (including `app/` correctness rules), Mypy, OpenAPI/SDK drift, published repository-contract drift/compatibility, repository gate, implementation release gate | all passed |
| `python -m pip_audit -r requirements/dev.txt` and `pnpm audit --audit-level high` | no known vulnerabilities in the committed dependency definitions |
| Deployment script syntax | all `deploy/scripts/*.sh` files passed `bash -n` in a cached Linux container |
| Strict `python scripts/release_gate.py` | fails closed only for `gpu_capacity`, `model_rights`, `ocr_evaluation`, `offline_install`, and `portrait_evaluation`; no implementation or report-digest errors remain |

Local results do not yet satisfy the measured target-GPU workload, per-model rights
records, fixed Portrait/OCR evaluation sets, or isolated Ubuntu offline-install
requirements. GPU count and memory are recorded as descriptive hardware evidence,
while qualification depends on the measured workload and five required scenario
outcomes; no fixed GPU-count or memory threshold is imposed by the deployment.
These items remain unchecked until reproducible objective evidence is recorded.

## Product matrix gates after 0.3.0

- Local username/password login, interactive sessions, identity-provider registration/probes, user lifecycle checks, and login-time Membership/Role scope resolution are implemented; signed OIDC/SAML/SCIM assertion exchange remains deployment-gated.
- Quota plans, fail-closed usage checks, billing accounts, idempotent metering, usage aggregation, and seat limits are implemented; payment settlement, invoices, taxes and self-service purchase remain deployment-gated.
- Project disable/restore/delete approval requests and audit retention policy/purge controls are implemented; tenant-scoped audit search and JSON/CSV export remain available.
- Annotation task/review plus provider probes, Edge device/sync/deployment acknowledgements, Search evaluation/ranking profiles with weighted retrieval plus index-backend/reranker probes, Flow run/condition/approval/webhook execution, Worker leases, and Agent least-scope approval/execution with trace/evaluation/memory records are implemented. Qdrant, Triton and MLflow provider boundaries plus thresholded automatic model rollback are implemented; real provider clusters, ANN/semantic model execution and model training remain gated. Kubernetes deployments and HPA are provided as a pre-production topology and still require target-cluster evidence.
- These capabilities must extend the shared IAM and product catalog instead of introducing per-product identity, authorization or deployment stacks.
- The current repository remains the platform integration repository. Model training stays in its existing professional repository; Data is split only after first-class dataset ownership and versioned handoff contracts are stable.
