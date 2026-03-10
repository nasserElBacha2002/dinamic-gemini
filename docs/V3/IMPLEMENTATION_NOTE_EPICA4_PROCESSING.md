# Épica 4 — Implementation Note: First operational processing/job flow

## 1. Backlog/doc interpretation for Épica 4

- **V3.0 Backlog Épica 5 (Jobs y orquestación)** defines the target:
  - **HU-5.1:** Create jobs associated with an aisle; frontend does not see job complexity; state at aisle level. Suggested: `EnqueueAisleProcessingUseCase`, `JobQueue.enqueue(job_type, payload) -> str`, `JobRepository.save(job)`, aisle status → QUEUED.
  - **HU-5.2:** Operator sees aisle state; `GET /aisles/{aisleId}` returns state; UI shows badges.
- **Documento técnico §7.8:** Job is internal; fields: id, target_type, target_id, job_type, status, payload_json, result_json, error_message, created_at, updated_at; association target_type=aisle, target_id=aisle_id.
- **Application ports:** `JobRepository` (save, get_by_id, get_latest_by_target) and `JobQueue` (enqueue(job_type, payload) -> str) are in `application/ports`; domain `Job` and `JobStatus` in `domain/jobs/entities.py`.
- **Contract tests** already expect `JobQueue.enqueue(job_type, payload) -> str` (e.g. StubJobQueue in test_ports_contract.py).
- **Épica 4 scope** (from spec): first operational slice only — trigger processing, see job/aisle status, refresh; no evidence/review/analytics. Duplicate active/running job prevention is implied by “invalid processing triggers” and “duplicate active/running jobs should not be allowed if domain/backlog implies that rule” — we will prevent starting when latest job for aisle is QUEUED or RUNNING.

## 2. Current state summary

- **Backend:** v3 inventories and aisles (use cases, SQL + memory repos, `/api/v3/inventories`, `/api/v3/inventories/{id}/aisles`). Domain Job and JobStatus exist; JobRepository and JobQueue ports exist. No v3 job persistence: legacy `jobs` table is pipeline-specific; no `JobRepository` implementation for v3; no `JobQueue` implementation satisfying `enqueue(job_type, payload) -> str` wired in API. Legacy queue is `enqueue(job_id)` in `src/jobs/queue.py`.
- **Frontend:** React + TS, MUI, inventory list/detail, create inventory/aisle, API client and types; InventoryDetail shows aisles table with code, status, created, error; no processing action or job status.

## 3. Backend files to create

- `src/database/schema_v3_jobs.sql` — v3_jobs table (or add to existing schema.sql).
- `src/infrastructure/repositories/sql_job_repository.py` — SqlJobRepository.
- `src/infrastructure/repositories/memory_job_repository.py` — MemoryJobRepository.
- `src/infrastructure/queue/v3_job_queue_adapter.py` — Adapter: enqueue(job_type, payload) -> uuid, enqueues id to legacy queue.
- `src/application/use_cases/start_aisle_processing.py` — StartAisleProcessingUseCase.
- `src/application/use_cases/get_aisle_processing_status.py` — GetAisleProcessingStatusUseCase.
- `src/api/schemas/processing_schemas.py` — ProcessAisleResponse, AisleStatusResponse, JobSummary.
- Tests: `tests/application/use_cases/test_start_aisle_processing.py`, `test_get_aisle_processing_status.py`, `tests/api/test_aisle_processing_v3.py` (or extend existing v3 API tests).

## 4. Backend files to modify

- `src/database/schema.sql` — Add v3_jobs table (prefer single schema file).
- `src/api/dependencies.py` — Add get_job_repo(), get_job_queue(), get_start_aisle_processing_use_case(), get_get_aisle_processing_status_use_case(); ensure inventory_id/aisle_id validation where needed.
- `src/api/routes/inventories_v3.py` — Add POST `/{inventory_id}/aisles/{aisle_id}/process`, GET `/{inventory_id}/aisles/{aisle_id}/status`; optionally extend list aisles to include latest_job.
- `src/api/schemas/aisle_schemas.py` — Add optional latest_job to AisleResponse (or a separate AisleWithJobResponse for list).
- `src/application/use_cases/__init__.py` — Export new use cases.
- `src/app.py` — Register new routes if needed (already under inventories_v3 router).

## 5. Frontend files to create

- None mandatory; optional: `frontend/src/utils/getApiErrorMessage.ts` for consistent error message extraction (deferrable per audit).

## 6. Frontend files to modify

- `frontend/src/api/types.ts` — Add JobSummary / AisleStatusResponse, ProcessAisleResponse.
- `frontend/src/api/client.ts` — Add startAisleProcessing(inventoryId, aisleId), getAisleStatus(inventoryId, aisleId); optionally extend getAisles response type if backend adds latest_job.
- `frontend/src/pages/InventoryDetail.tsx` — Add “Process” action per aisle, loading/disabled state, success/error feedback; show latest job status (chip/text); refresh (re-fetch aisles after start or manual refresh button).

## 7. Backend design summary

- **v3 jobs table:** New table `v3_jobs` (id PK, target_type, target_id, job_type, status, payload_json, result_json, error_message, created_at, updated_at) to avoid conflating with legacy `jobs`. Index (target_type, target_id) for get_latest_by_target.
- **StartAisleProcessingUseCase:** Validate aisle exists (and optionally that it belongs to inventory if we pass inventory_id); if latest job for aisle is QUEUED or RUNNING, raise conflict; generate job_id via JobQueue.enqueue("process_aisle", {"aisle_id": aisle_id}) — adapter returns id and enqueues that id to legacy queue; create domain Job, save; aisle.mark_queued(now); save aisle; return job id (or job).
- **GetAisleProcessingStatusUseCase:** Load aisle by id; if not found raise; load latest job by target_type=aisle, target_id=aisle_id; return DTO with aisle + latest_job (id, status, updated_at).
- **JobQueue adapter:** Implements application port `JobQueue`. enqueue(job_type, payload): generate uuid, call legacy `queue.enqueue(job_id)`, return job_id. Use case is responsible for persisting Job.
- **API:** POST `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process` → 202 Accepted + { job_id }; 404 if inventory/aisle not found or aisle not in inventory; 409 if aisle already has active job. GET `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` → { aisle, latest_job }; 404 if not found. List aisles response extended with optional `latest_job` per aisle so list view can show status without N+1.
- **Errors:** AisleNotFoundError (404), InventoryNotFoundError (404), ActiveJobExistsError (409). Routes map to HTTP and do not contain business logic.

## 8. Frontend design summary

- **Trigger:** Button “Process” (or “Start processing”) per row in aisle table; disabled when aisle status is QUEUED or PROCESSING or when no permission; loading state during POST; on success show brief success and re-fetch aisles (and optionally status for that aisle); on error show message in alert or inline.
- **Status:** Show aisle status (existing chip); next to it or in new column show “Latest job: queued/running/succeeded/failed” and updated_at if available (from list response latest_job or from status endpoint).
- **Refresh:** Re-fetch aisles after starting process; optional “Refresh” button to reload aisles (and thus latest_job). No polling or WebSockets in this epic.
- **API client:** startAisleProcessing(inventoryId, aisleId) -> Promise<{ job_id }>; getAisleStatus(inventoryId, aisleId) -> Promise<{ aisle, latest_job }>; types for JobSummary and response shapes aligned with backend.

## 9. Risks / decisions

- **Legacy queue vs v3:** Legacy worker consumes job_id from queue and expects legacy job_store/DB. We will enqueue v3 job ids; worker does not yet handle v3 jobs (no worker change in this epic). Jobs will remain QUEUED (or we add a minimal v3 worker that only updates status). Document as deferred: “Worker integration: v3 job consumption and status updates in a future epic.”
- **Table name:** Use `v3_jobs` to avoid collision with legacy `jobs` and FKs (pallet_results, job_events reference legacy jobs.id).
- **Conflict rule:** Prevent starting when latest job for aisle is QUEUED or RUNNING; return 409 with clear message.
- **List response extension:** Add `latest_job?: { id, status, updated_at }` to aisle list so UI can show status without extra per-aisle calls; keep endpoint backward compatible (new optional field).

---

*Implementation will follow Phase 2 (backend) then Phase 3 (frontend).*
