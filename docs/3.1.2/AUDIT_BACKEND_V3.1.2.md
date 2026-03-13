# AUDIT_BACKEND_V3.1.2.md

## 1. Summary

This document reports the technical audit of the backend for Dinamic Inventory v3.1.2. It inventories routes, handlers, use cases, repositories, DTOs/schemas, and identifies active vs deprecated/legacy/unused artifacts.

## 2. Scope

- **Included:** `src/api/`, `src/application/`, `src/domain/`, `src/infrastructure/` (repositories, pipeline adapters, storage, queue), `src/jobs/`, `src/database/`, `src/runtime/`, `src/config.py`, and API-related schemas in `src/api/schemas/`.
- **Excluded:** Pure pipeline/CV modules (detection, tracking, reid, video, etc.) except where they are invoked by API or job execution; no changes were applied.

## 3. Findings

### 3.1 Route inventory

**Registered routers** (from `src/api/server.py`):


| Router                | Prefix                   | File                               | Classification                                                                                                     |
| --------------------- | ------------------------ | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| jobs_router           | `/api/v1/inventory/jobs` | `src/api/routes/jobs.py`           | **Active** (partially consumed: create job, status, result, report, artifacts; entities router shares same prefix) |
| entities_router       | `/api/v1/inventory/jobs` | `src/api/routes/entities.py`       | **Active** (frontend consumes `GET .../entities` only)                                                             |
| inventories_v3_router | `/api/v3/inventories`    | `src/api/routes/inventories_v3.py` | **Active** (primary frontend API)                                                                                  |


**Endpoints by router:**

**jobs.py** (`/api/v1/inventory/jobs`):

- `POST ""` → create job (video or photos upload) — **Active** (legacy/v1 flow; used when creating job from upload UI or external trigger).
- `GET "/{job_id}"` → job status — **Active** (consumed by legacy flows / Stage 8 DB).
- `GET "/{job_id}/result"` → job result (report JSON or DB fallback) — **Active**.
- `GET "/{job_id}/report"` → raw report (optional `resolved`) — **Active**.
- `GET "/{job_id}/artifacts"` → artifacts list — **Active**.

**entities.py** (same prefix `/api/v1/inventory/jobs`):

- `GET "/{job_id}/entities"` → list entities with optional filters — **Active** (frontend: `getJobEntities` in `client.ts`).
- `GET "/{job_id}/entities/{entity_uid}/evidence"` → entity evidence — **Active** (consumption: Unclear / may be used by entity-detail or evidence views).
- `POST "/{job_id}/entities/{entity_uid}/review"` → submit review — **Active**.
- `GET "/{job_id}/entities/{entity_uid}/audit"` → entity audit trail — **Active**.

**inventories_v3.py** (`/api/v3/inventories`):

- `POST ""`, `GET ""`, `GET "/{inventory_id}"` — inventories CRUD — **Active**.
- `GET "/{inventory_id}/metrics"` — inventory metrics — **Active**.
- `POST "/{inventory_id}/aisles"`, `GET "/{inventory_id}/aisles"` — aisles — **Active**.
- `POST "/{inventory_id}/aisles/{aisle_id}/process"`, `GET ".../status"` — process aisle, status — **Active**.
- `GET ".../jobs/{job_id}/execution-log"` — execution log — **Active**.
- `POST ".../assets"`, `GET ".../assets"`, `GET ".../assets/{asset_id}/file"` — assets and file — **Active**.
- `GET ".../positions"`, `GET ".../positions/{position_id}"`, `POST ".../positions/{position_id}/reviews"` — positions and reviews — **Active**.

**Other:** `GET /health` — **Active** (no auth).

### 3.2 Route consumers (evidence)

- **v3 endpoints:** Consumed by `frontend/src/api/client.ts` (getInventories, getAisles, getAisleStatus, getExecutionLog, uploadAisleAssets, getAisleAssets, getReferenceImageFileUrl, getAislePositions, getPositionDetail, submitReviewAction). All v3 routes listed above have a corresponding client function or URL builder.
- **v1 endpoints:** `getJobEntities(jobId)` calls `GET /api/v1/inventory/jobs/{jobId}/entities`. No other frontend references to v1 job/entity endpoints were found in the client. Usage of `GET .../result`, `.../report`, `.../artifacts`, `.../entities/{uid}/evidence`, `.../review`, `.../audit` may be from legacy UI, tests, or external tools — **Unclear / Requires manual confirmation** for full consumer list.

### 3.3 Handlers / controllers

- **Thin route layer:** Route functions in `inventories_v3.py` delegate to use cases via `Depends()`; no business logic in routes. Same pattern in `entities.py` (direct report/manifest access and helpers). `jobs.py` mixes request handling with job_store, DB repos, and file I/O.
- **Overlap:** `jobs.py` and `entities.py` share the same prefix; both are under "v1" and conceptually job-centric. No duplicate route paths.

### 3.4 Services / use cases

**Use cases used by v3 routes** (from `src/api/dependencies.py` and `inventories_v3.py`):

- CreateInventoryUseCase, GetInventoryUseCase, ListInventoriesUseCase, GetInventoryMetricsUseCase — **Active**.
- CreateAisleUseCase, ListAislesByInventoryUseCase (via list_aisles), ListAislesWithStatusUseCase (via status), GetAisleProcessingStatusUseCase — **Active**.
- StartAisleProcessingUseCase, UploadAisleAssetsUseCase, ListAisleAssetsUseCase — **Active**.
- ListAislePositionsUseCase, GetPositionDetailUseCase, ConfirmPositionUseCase, UpdateProductQuantityUseCase, UpdateProductSkuUseCase, DeletePositionUseCase — **Active**.
- PersistAisleResultUseCase — **Active** (used by V3JobExecutor, not directly by routes).

**Use cases not referenced by any route:** None identified; all application use cases in `src/application/use_cases/` are either used by v3 routes or by the v3 job executor / pipeline.

### 3.5 Repositories / adapters

**Ports** (`src/application/ports/repositories.py`): InventoryRepository, AisleRepository, SourceAssetRepository, PositionRepository, ProductRecordRepository, EvidenceRepository, ReviewActionRepository, JobRepository — all **Active** (used by v3 deps or executor).

**Implementations:**

- **SQL:** `src/infrastructure/repositories/sql_*.py` (inventory, aisle, position, product_record, evidence, source_asset, review_action, job) — **Active** when `sqlserver_enabled`.
- **Memory:** `src/infrastructure/repositories/memory_*.py` — **Active** (fallback or when DB disabled).
- **Stage 8 DB** (`src/database/repository.py`): JobsRepository, PalletResultsRepository, JobEventsRepository — **Active** for legacy job flow (jobs table, pallet_results, job_events); used by `jobs.py` and `jobs/worker.py`.

**Adapters:** V3ArtifactStorageAdapter (`v3_artifact_storage_adapter.py`), V3JobQueueAdapter — **Active**. JobStoreAdapter, MemoryQueueAdapter — **Active** (job queue).

### 3.6 DTOs / schemas / mappers

**Request/response schemas** (`src/api/schemas/`): aisle_schemas, asset_schemas, inventory_schemas, position_schemas, processing_schemas, requests, responses — all referenced by active routes. **Active.**

**Pydantic models in `responses.py`:** Used by both jobs and entities routers; some fields (e.g. traceability, source_image_original_filename) documented as optional for Epic 3.1 / 5. **Active.**

**Mappers:** `v3_report_mapper.py` (map_hybrid_report_to_domain) — **Active** (persist_aisle_result, executor). No unused DTOs identified.

### 3.7 Dead modules / imports

- **app.py:** `src/app.py` exists; server entrypoint is `src.api.server:app`. **Unclear** whether `app.py` is used (e.g. by another runner); if not, it may be **Legacy** or duplicate entrypoint.
- **photos_handler.py:** Used by `jobs.py` for photos upload path. **Active.**

## 4. Classification


| Category       | Count                                                                                 | Notes                                |
| -------------- | ------------------------------------------------------------------------------------- | ------------------------------------ |
| **Active**     | All v3 routes, v3 use cases, v3 repos, v3 schemas, job/entity routes and their deps   | Primary product surface              |
| **Deprecated** | None explicitly marked                                                                | —                                    |
| **Legacy**     | v1 job/entity routes; Stage 8 `jobs`/`pallet_results`/`job_events` repos              | Still used by worker and possibly UI |
| **Unclear**    | Consumer of v1 result/report/artifacts/entity evidence/review/audit; role of `app.py` | Requires manual confirmation         |


## 5. Risks

- **Removing v1 routes:** If any consumer (frontend screen, integration, or script) still calls v1 result/report/artifacts or entity evidence/review/audit, removal would break it. Audit recommends tracing all v1 usages before any deletion.
- **Removing Stage 8 repos:** Legacy worker and job creation (video/photos) depend on `jobs` table and pallet_results; v3 process_aisle uses `v3_jobs` and application repos. Both coexist; removing legacy job flow requires a separate migration.

## 6. Recommendations

- Trace every v1 endpoint to a known consumer (frontend, test, or doc); mark as "active with consumer" or "candidate for removal."
- Unify or document the two job systems (legacy `jobs` + Stage 8 vs v3 `v3_jobs` + executor) so cleanup stages can safely remove one path.
- Confirm `app.py` vs `api/server.py` entrypoint usage; remove or redirect if redundant.

## 7. Candidate next-stage actions

- **Stage 2 (Backend legacy cleanup):** After confirming consumers, remove any v1 route that has no consumer; remove dead code in `jobs.py`/`entities.py` that only served removed routes.
- Consolidate job-related entrypoints and document which flow (v1 vs v3) is supported for which use case.
- Remove or repurpose unused DTOs/schemas only after contract audit confirms no use.

