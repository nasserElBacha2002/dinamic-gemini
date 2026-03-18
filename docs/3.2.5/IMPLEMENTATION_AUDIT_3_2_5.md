# Release 3.2.5 — Block C: v3 Technical Consolidation
## Phase 1 — Active v3 surface audit (IMPLEMENTATION_AUDIT_3_2_5)

**Repo**: Dinamic Inventory  
**Date**: 2026-03-18  
**Goal of this document**: inventory the *actually mounted* API surface and the *actually consumed* frontend contracts, detect inconsistencies/legacy leaks, and define the **recommended order of changes** for Release 3.2.5.

This document is intentionally grounded in code locations (files) so later phases can reference concrete sources of truth.

---

## 1) Backend entrypoints and router mounting

### 1.1 FastAPI app wiring

- **FastAPI app**: `backend/src/api/server.py`
  - Mounts only:
    - `v3_router` from `src.api.routes.v3`
    - `auth_router` from `src.auth.routes`
  - Healthcheck:
    - `GET /health`
  - Optional middleware:
    - `X-API-Key` required when `settings.api_key` is set (skips `/health`)

**Initial conclusion**: The backend is *intended* to expose only v3 inventory operations plus auth. We still need to verify there are no *indirect* legacy code paths (e.g. job store, artifact reading conventions) affecting v3 endpoints.

### 1.2 v3 root router and prefix model

- **v3 root router**: `backend/src/api/routes/v3/router.py`
  - Base prefix: **`/api/v3/inventories`**
  - Router-level dependency: `Depends(get_current_admin)` (all v3 routes require auth)
  - Includes sub-routers:
    - `inventories.py`
    - `aisles.py`
    - `assets.py`
    - `positions.py`
    - `reviews.py`

---

## 2) Active backend route surface (v3 + auth)

This is the *currently active* API surface as defined by mounted routers.

### 2.1 Auth (non-v3 prefix)

Source: `backend/src/auth/routes.py`

- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/refresh`
- `POST /auth/logout` (204)

### 2.2 v3 Inventories

Source: `backend/src/api/routes/v3/inventories.py` (mounted under `/api/v3/inventories`)

- `POST /api/v3/inventories/`
  - body: `CreateInventoryRequest`
  - response: `InventoryResponse` (201)
- `GET /api/v3/inventories/`
  - response: `List[InventoryResponse]`
- `GET /api/v3/inventories/{inventory_id}`
  - response: `InventoryResponse`
- `GET /api/v3/inventories/{inventory_id}/metrics`
  - response: `InventoryMetricsResponse`
- `POST /api/v3/inventories/{inventory_id}/visual-references`
  - multipart: `files: List[UploadFile]`
  - response: `UploadInventoryVisualReferencesResponse` (201)
- `GET /api/v3/inventories/{inventory_id}/visual-references`
  - response: `InventoryVisualReferenceListResponse`
  - ordering contract stated in docstring: **created_at ASC, id ASC**

### 2.3 v3 Aisles + Jobs (aisle processing lifecycle)

Source: `backend/src/api/routes/v3/aisles.py`

- `POST /api/v3/inventories/{inventory_id}/aisles`
  - response: `AisleResponse` (201)
- `GET /api/v3/inventories/{inventory_id}/aisles`
  - response: `List[AisleResponse]`
  - includes `latest_job` summary
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process`
  - response: `ProcessAisleResponse` (202)
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status`
  - response: `AisleStatusResponse` (aisle + latest_job)
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel`
  - response: empty (202)
  - cancellation semantics described in docstring (QUEUED → CANCELED, RUNNING → CANCEL_REQUESTED → CANCELED)
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log`
  - response: `ExecutionLogResponse`

### 2.4 v3 Aisle assets (upload/list/file serving)

Source: `backend/src/api/routes/v3/assets.py`

- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets`
  - response: `UploadAisleAssetsResponse` (201)
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets`
  - response: `List[SourceAssetResponse]`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file`
  - response: `FileResponse`
  - optional query: `job_id` for HEIC normalized preview resolution

### 2.5 v3 Positions (results)

Source: `backend/src/api/routes/v3/positions.py`

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions`
  - response: `PositionListResponse`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}`
  - response: `PositionDetailResponse` (includes evidences + review_actions)

### 2.6 v3 Reviews (manual operations)

Source: `backend/src/api/routes/v3/reviews.py`

- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews`
  - request: `ReviewActionRequest`
  - response: empty (204)

---

## 3) Frontend active API surface (what the UI actually calls)

### 3.1 API client

Source: `frontend/src/api/client.ts`

All inventory operations are executed against `/api/v3/*`:

- `getInventories()`, `getInventory(id)`, `createInventory()`
- `getInventoryMetrics(inventoryId)`
- `uploadInventoryVisualReferences(inventoryId, files)`, `getInventoryVisualReferences(inventoryId)`
- `getAisles(inventoryId)`, `createAisle(inventoryId, body)`
- `uploadAisleAssets(inventoryId, aisleId, files)`, `getAisleAssets(inventoryId, aisleId)`
- `startAisleProcessing(inventoryId, aisleId)`, `getAisleStatus(inventoryId, aisleId)`
- `getExecutionLog(inventoryId, aisleId, jobId)`
- (also: position endpoints + review actions; see rest of file)

**Initial conclusion**: Frontend appears already consolidated to v3 endpoints; any “legacy mixing” for this release is more likely to be:
- legacy semantics inside v3 DTO fields
- legacy artifact path conventions being surfaced
- job lifecycle/state divergence between layers

---

## 4) Contract / semantics inconsistencies detected (initial)

This section lists **concrete issues already visible** from the route + schema + frontend type scan. This is not exhaustive yet; it’s the Phase 1 starting inventory.

## 4.0 Runtime sources of truth (v3 vs legacy)

This subsection answers “what is real at runtime” beyond router mounting. Key takeaway: the HTTP surface is v3-only, but **two job systems coexist** (v3 DB-backed jobs and Stage-7 legacy job records) and the platform still depends on **filesystem artifacts** for operator/debug affordances.

### v3 repositories (authoritative when SQL Server is enabled)

- **Repo wiring / source of truth selection**: `backend/src/runtime/v3_deps.py`
  - When `sqlserver_enabled=true` and a connection string exists:
    - v3 repos use SQL implementations (e.g. `SqlJobRepository`, `SqlPositionRepository`, `SqlEvidenceRepository`).
  - Otherwise:
    - v3 repos use in-memory implementations (dev/test fallback).
- **v3 jobs**: SQL table `inventory_jobs` (domain `Job`) via:
  - `backend/src/infrastructure/repositories/sql_job_repository.py`
  - DB schema: `backend/src/database/schema.sql` (`inventory_jobs`)

### Filesystem artifacts (still required for v3 operator/debug paths)

- **Execution log**: `output_dir/<job_id>/run/execution_log.jsonl`
  - Writer/reader: `backend/src/pipeline/execution_log.py`
  - Served via v3 route: `backend/src/api/routes/v3/aisles.py` (`.../execution-log`)
- **Hybrid report**: `output_dir/<job_id>/run/hybrid_report.json`
  - Used by executor/persist + traceability enrichment logic
  - Enrichment helper reads it best-effort and caches: `backend/src/api/routes/v3/shared.py`
- **HEIC normalized preview**: depends on `output_dir/<job_id>/input_manifest.json` + normalized file under the run dir
  - Resolver: `backend/src/api/routes/v3/shared.py::resolve_normalized_asset_path(...)`
  - Served via asset file route: `backend/src/api/routes/v3/assets.py` with optional `job_id` query

### Legacy Stage-7 job store (not v3 source of truth, but coexists in the same process)

- **Legacy job store** persists `JobRecord` under `output/<job_id>/job.json` and (optionally) pushes to legacy SQL tables `jobs/pallet_results/job_events`.
  - Implementation: `backend/src/jobs/job_store.py`
  - Models: `backend/src/jobs/models.py` (legacy `JobStatus` without cancel states)
- **Worker flow** tries v3 job execution first and falls back to legacy job execution:
  - `backend/src/jobs/worker.py` calls `_try_v3_process_aisle(...)` before running legacy `get_job/update_job(...)`.

**Impact**: Release 3.2.5 should make it explicit and test-protected that v3 API + v3 execution **never depend** on Stage-7 job status semantics, even though the fallback branch still exists for non-v3 jobs.

### 4.1 Job status enum divergence (high risk)

- v3 domain job status includes cancellation states:
  - Source: `backend/src/domain/jobs/entities.py` → `JobStatus`
  - Includes: `cancel_requested`, `canceled`, `timed_out` (reserved)
- Legacy job record model (Stage 7 job store) does **not** include cancellation states:
  - Source: `backend/src/jobs/models.py` → `JobStatus`
  - Only: `queued`, `running`, `succeeded`, `failed`

**Why this matters for 3.2.5**:

- v3 routes already expose cancellation (`POST .../cancel`) and job summaries in aisle status/list responses.
- If any path still serializes through legacy `JobRecord` (or persists/reads statuses from it), frontend will see inconsistent states or lose cancellation semantics.

**Audit follow-up needed**:

- Identify which persistence layer is authoritative for v3 jobs (`inventory_jobs` / SQL repos) vs legacy job store (`output/<job_id>/job.json`).
- Identify what the worker/executor updates and what status endpoints read.

### 4.1.1 Job lifecycle read/write map (v3)

Concrete “who writes / who reads” references:

- **Write path**
  - Create/enqueue: `backend/src/application/use_cases/start_aisle_processing.py`
    - Persists `Job(status=queued)` via `JobRepository.save(...)`
  - Cancel request: `backend/src/application/use_cases/cancel_aisle_job.py`
    - `queued → canceled`, `running → cancel_requested`, idempotent on `cancel_requested`
  - Execute + final transitions: `backend/src/infrastructure/pipeline/v3_job_executor.py`
    - `queued → running → succeeded/failed`
    - Observes `cancel_requested` before start and after pipeline run and marks `canceled`
- **Read path**
  - Aisle list latest job: `backend/src/application/use_cases/list_aisles_with_status.py`
    - Uses `JobRepository.get_latest_by_targets(...)` (batch)
  - Aisle status latest job: `backend/src/application/use_cases/get_aisle_processing_status.py`
    - Uses `JobRepository.get_latest_by_target(...)`
  - Execution log API: `backend/src/api/routes/v3/aisles.py`
    - Validates job/aisle/inventory via repositories, then reads filesystem execution log
    - Log file implementation: `backend/src/pipeline/execution_log.py`

### 4.2 Mixed validation semantics in upload adaptation (medium risk)

- Inventory visual references upload adaptation **fails fast** and returns explicit 422 for invalid parts.
  - Source: `backend/src/api/routes/v3/inventories.py` → `_to_uploaded_visual_reference_files`
- Aisle assets upload adaptation currently *skips* malformed items (`continue` when both filename and content_type missing).
  - Source: `backend/src/api/routes/v3/assets.py`

**Why it matters**: creates inconsistent client expectations; also makes debugging harder (some uploads silently dropped).

**Potential consolidation task for 3.2.5**:

- Unify upload adaptation across endpoints: either strict fail-fast everywhere or consistent per-part error contracts.

### 4.3 Evidence / artifact path semantics likely leak infra detail (needs systematic check)

Current v3 DTOs expose `storage_path` for:

- `SourceAssetResponse` (`assets.py`, `asset_schemas.py`)
- `EvidenceResponse` (`position_schemas.py`)

Inventory visual references explicitly **do not** expose storage path:

- `InventoryVisualReferenceResponse` docstring in `inventory_schemas.py`

**Why it matters**:

- “Consolidate artifacts and persistence” goal of 3.2.5 suggests we should ensure frontend consumes a coherent “evidence/artifact contract” and doesn’t need to infer filesystem layout.
- Today, the frontend type `SourceAssetSummary.storage_path` is present but annotated “not used”.

**Audit follow-up needed**:

- Identify which artifact URLs are used by the frontend (e.g. `getReferenceImageFileUrl(...)`).
- Verify that path exposure is necessary and consistent vs using file-serving endpoints.

### 4.3.1 Artifact consumption reality (frontend)

What the frontend *actually* uses to render artifacts/evidence today:

- **Source image preview (Result detail)**:
  - URL builder: `frontend/src/api/client.ts::getReferenceImageFileUrl(...)`
  - UI panel: `frontend/src/features/results/components/detail/ResultEvidencePanel.tsx`
  - Image fetching: `frontend/src/features/results/hooks/useEvidenceImageLoad.ts` via `fetchEvidenceImage(...)`
- **Notably, the UI does not use**:
  - `EvidenceResponse.storage_path` to render images (currently metadata-only in UI mapping)

**Implication**: `storage_path` fields in evidence/asset DTOs are likely not required for current UI flows and should be reviewed in Phase 2/4 for contract cleanliness.

### 4.4 API version string likely misleading (low risk, hygiene)

`backend/src/api/server.py` sets:

- `FastAPI(..., version="2.0.0")`

Given the system is consolidating toward **v3**, this version metadata may mislead operators/devs and should be reviewed in 3.2.5 (documentation/observability impact).

### 4.5 Frontend compensation points (contract not yet fully “closed”)

Even though the frontend calls only v3 routes, it still carries compatibility fallbacks that indicate historical or backend contract non-uniformity:

- **Results mapping fallbacks**: `frontend/src/features/results/mappers/positionToResult.ts`
  - `hasEvidence`: `p.has_evidence ?? Boolean(p.primary_evidence_id)`
  - `sourceImageId` / `sourceFileName`: fallback to `detected_summary_json` if typed fields are missing
  - `qtySource` default: `'detected'` if missing
  - `traceability_status`: coerces unknown values to `UNVALIDATED`
- **Evidence preview** uses stable file-serving route rather than evidence storage paths:
  - URL builder: `frontend/src/api/client.ts::getReferenceImageFileUrl(...)`
  - UI: `frontend/src/features/results/components/detail/ResultEvidencePanel.tsx`

**Impact**: Phase 2 contract alignment should aim to (a) reduce reliance on `detected_summary_json` for typed fields and (b) make “source image preview” a stable contract without requiring frontend inference.

---

## 5) Legacy routes still exposed?

As of this audit pass:

- FastAPI app mounts only `v3_router` and `auth_router` (`backend/src/api/server.py`).
- No other routers are included.

**Initial conclusion**: There are no “legacy HTTP routes” mounted.

**Important caveat**: “Legacy” may still exist as:

- persistence/worker models (job store vs SQL),
- artifact file naming/layout conventions,
- DTO fields with legacy semantics,
- metadata dict fallbacks.

---

## 6) Suggested order of changes (for Release 3.2.5)

This is the recommended execution order to minimize churn and prevent contract breakage.

1. **Complete Phase 1 audit** (this document) by expanding:
  - full DTO inventory for jobs/positions/review/evidence/artifacts
  - identify authoritative persistence per entity (SQL vs filesystem job store)
  - identify artifact URLs actually consumed by the frontend
2. **Phase 2 contract alignment**
  - normalize/rename ambiguous fields
  - remove “frontend compensation” logic by fixing backend contracts
3. **Phase 3 job lifecycle hardening**
  - define and enforce the v3 job state machine end-to-end
  - resolve job status enum divergence
4. **Phase 4 artifacts + persistence alignment**
  - ensure every artifact referenced by API is accessible via stable routes
  - remove reliance on storage paths as public contract where feasible
5. **Phase 5 positions/results consolidation**
  - make count origin + review reasons + manual correction semantics explicit
6. **Phase 6 review operations + audit trail**
7. **Phase 7 debugging/observability**
8. **Phase 8 release closure report**

---

## 7) Next concrete inspection steps (to finish Phase 1)

Backend:

- `backend/src/api/dependencies.py` (wiring of repos/use cases; identify persistence sources)
- `backend/src/infrastructure/repositories/sql_job_repository.py` (authoritative job persistence?)
- `backend/src/infrastructure/pipeline/v3_job_executor.py` (state transitions, result persistence, artifacts)
- `backend/src/jobs/job_store.py`, `backend/src/jobs/worker.py` (legacy job store usage; any v3 coupling)
- `backend/src/api/routes/v3/shared.py` (evidence/traceability enrichment; artifact reading from output)

Frontend:

- `frontend/src/features/results/`* (result mapping; any compensation logic)
- `frontend/src/pages/*` for where evidence and artifacts are displayed

Docs:

- Keep this audit updated as discoveries are made while proceeding to Phase 2+.

---

## 8) Phase 3 — Job Lifecycle Hardening (Block 1)

Lifecycle hardening has started. The **v3 job-state authority** is being formalized so that:

- The active v3 API reads/writes job state only via **domain `Job`/`JobStatus`** and **`JobRepository`** (no dependence on Stage-7 `JobRecord` or `src.jobs.models.JobStatus`).
- Cancel-state semantics (QUEUED→CANCELED, RUNNING→CANCEL_REQUESTED, CANCEL_REQUESTED→CANCELED, terminal reject) are explicit and test-protected.

**Reference**: See **`docs/3.2.5/JOB_LIFECYCLE_3_2_5.md`** for the documented source of truth, write/read paths, cancel transitions, DB vs filesystem relationship, and legacy coexistence. Tests added in this block cover: queued-job cancel (202 + list/status show `canceled`), terminal-job cancel (409), and use-case-level cancel transitions; they demonstrate that active v3 lifecycle behavior does not depend on the legacy job store.

---

## 9) Phase 3 — Job Lifecycle Hardening (closure)

Phase 3 lifecycle hardening is **complete**. The v3 job-state authority has been formalized, and the following are documented and test-protected:

- **Source of truth**: Active v3 API and executor use only `JobRepository` and domain `Job`/`JobStatus`; no dependence on Stage-7 or legacy job store for v3 behavior.
- **Cancel contract**: QUEUED→CANCELED, RUNNING→CANCEL_REQUESTED, CANCEL_REQUESTED→CANCELED, terminal reject; list/status expose cancel states correctly (route-level tests).
- **Retry / re-processing boundary**: QUEUED, RUNNING, CANCEL_REQUESTED block `POST .../process` (409); CANCELED, FAILED, SUCCEEDED, TIMED_OUT allow a new job (202). Documented in `JOB_LIFECYCLE_3_2_5.md` §5; route-level tests cover active-job block and post-terminal new job.
- **Historical reads**: Job state and latest-job come from DB; execution-log is best-effort from filesystem. Missing artifacts do not affect lifecycle status; execution-log returns 200 with empty events when run dir is missing. Documented in `JOB_LIFECYCLE_3_2_5.md` §6; route-level test confirms status and execution-log contract when artifacts are absent.

The repository is ready to proceed to the next phase. Deferred items (explicit retry product semantics, historical job list, artifact retention policy, legacy fallback removal) are recorded in `JOB_LIFECYCLE_3_2_5.md` §9.

