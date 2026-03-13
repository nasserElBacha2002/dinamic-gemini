# AUDIT_JOB_LIFECYCLE_V3.1.2.md

## 1. Summary

This document reports the job lifecycle and cancellation audit for Dinamic Inventory v3.1.2. It documents current job states, transitions, persistence, long-running stages, and recommends where cancellation and timeout can be integrated.

## 2. Scope

- **Included:** v3 domain Job (process_aisle), legacy job record (jobs table), worker flow, V3JobExecutor, pipeline stages, frontend job status consumption.
- **Excluded:** No implementation of cancellation or timeout; audit only.

## 3. Findings

### 3.1 Current job states (v3)

**Domain entity** (`src/domain/jobs/entities.py`):

- **JobStatus:** QUEUED, RUNNING, SUCCEEDED, FAILED. No cancel_requested, canceled, or timed_out.

**Persistence:** `v3_jobs` table stores id, target_type, target_id, job_type, status, payload_json, result_json, error_message, created_at, updated_at. Status is a string; application maps to JobStatus enum.

### 3.2 State transitions (v3 process_aisle)

1. **Creation:** StartAisleProcessingUseCase creates Job (QUEUED), saves via JobRepository, enqueues job_id to queue. No direct write to legacy `jobs` table for this path.
2. **Dequeue:** Worker thread (server startup) calls `dequeue()`; gets job_id. Worker calls `_try_v3_process_aisle(base_path, job_id)`.
3. **Execution:** V3JobExecutor.execute loads job, loads aisle and assets, marks job RUNNING (and aisle processing), runs pipeline, on success marks SUCCEEDED and persists result_json and aisle; on failure marks FAILED and sets error_message. All state changes go through JobRepository.save and AisleRepository.save.
4. **No intermediate checkpoints:** Once the pipeline runs, there is no in-loop check for "cancel requested" or timeout. Pipeline runs to completion or exception.

### 3.3 Where state is persisted

- **v3:** JobRepository (SqlJobRepository or MemoryJobRepository). Save is called on: create (StartAisleProcessingUseCase), status update to RUNNING, SUCCEEDED (with result_json), FAILED (with error_message). Aisle status (processing / processed / error) is persisted in AisleRepository.
- **Legacy:** jobs table via database/repository.py JobsRepository; worker updates status, progress, outputs, and inserts pallet_results and job_events. Separate from v3_jobs.

### 3.4 Long-running stages

Pipeline (HybridInventoryPipeline) and executor run in sequence:

- Input preparation (manifest, normalize photos)
- Frame acquisition
- Analysis (Gemini)
- Entity resolution
- Evidence stage
- Reporting

Longest typically: **Analysis** (LLM calls) and **Input preparation** (normalization). No sub-step yields control back to a "check cancel" point today.

### 3.5 Timeout behavior

- **No timeout policy** found in config or executor. A stuck job (e.g. hung HTTP call to Gemini) would run until process kill or success/failure.
- Worker thread runs indefinitely (dequeue loop); no per-job timeout. **Gap** for v3.1.2 goal (timeout long-running jobs).

### 3.6 Frontend visibility

- **Aisle status:** GET .../aisles/{aid}/status returns aisle + latest_job (id, status, created_at, updated_at, error_message). Frontend polls or fetches once; shows job status and error. **Sufficient** for current UX.
- **Execution log:** GET .../jobs/{jid}/execution-log returns events; frontend shows them in ExecutionLogPanel. No "cancel" button or cancel_requested state today.
- **Missing for cancellation:** Frontend has no endpoint to POST "cancel job" and no status values for cancel_requested/canceled/timed_out. Would need API and UI addition in Stage 6.

### 3.7 Safe cancellation checkpoints

Recommended places to check a "cancel requested" flag (or timeout) without corrupting state:

1. **Before pipeline start** (in V3JobExecutor after loading job/aisle/assets): if cancel requested, mark job canceled and exit.
2. **Between pipeline stages** (e.g. after input preparation, after frame acquisition, after analysis): each stage returns; executor can check flag before calling next stage. Requires pipeline to expose stages as callable steps or executor to drive a state machine.
3. **Not inside a single blocking call** (e.g. inside one Gemini request): cooperative cancellation only at step boundaries.

Current pipeline API: single `run()` or equivalent; stages are internal. **Refactor needed** to expose step boundaries for checkpoint checks (or add a simple check only at start and between a small set of "phase" boundaries if pipeline can be split without major rewrite).

### 3.8 Legacy job flow (brief)

Legacy job: created via POST /api/v1/inventory/jobs (video or photos), written to `jobs` table, enqueued. Worker, if not v3, runs HybridInventoryPipeline with job dir and updates `jobs` and pallet_results. No cancellation or timeout there either. **Out of scope** for v3 cancellation design unless product retires legacy.

## 4. Classification

| Item | Classification | Note |
|------|----------------|------|
| v3 JobStatus | **Active** | QUEUED, RUNNING, SUCCEEDED, FAILED |
| v3 persistence | **Active** | JobRepository → v3_jobs |
| Pipeline checkpoints | **Missing** | No cancel or timeout check |
| Timeout policy | **Missing** | No config or enforcement |
| Frontend job state | **Active** | latest_job, execution log |

## 5. Risks

- Adding cancel_requested/canceled/timed_out without persisting them in v3_jobs would leave frontend and API out of sync with reality. Schema and repository must support new status values.
- Checking cancellation only at executor level (e.g. once before pipeline) is safe but may leave long-running pipeline runs unstoppable until the next major refactor (stage-level checkpoints).

## 6. Recommendations

- **Cooperative cancellation:** Add a "cancel requested" flag (e.g. in v3_jobs or a small side table/key-value). Worker or executor checks it at defined points (before pipeline, and if possible between stages). When set, mark job canceled and exit cleanly.
- **New states:** Add cancel_requested (optional; could be implicit from a separate "cancel" table), canceled, timed_out. Persist in v3_jobs.status and expose in GET .../status and GET .../positions (if job summary is embedded).
- **Timeout:** Add config (e.g. max_job_duration_seconds). Before or after each pipeline stage, compare elapsed time; if exceeded, mark job timed_out and stop. Requires a single place that measures elapsed time (e.g. executor).
- **Checkpoints:** Prefer refactoring pipeline or executor so that "run next stage" is explicit; then insert one checkpoint check between stages. If refactor is too large for v3.1.2, implement only "cancel before pipeline start" and "timeout at start of next poll" (worker checks duration when picking next job or in a wrapper around executor.execute).

## 7. Candidate next-stage actions

- **Stage 6 (Job cancellation):** (1) Add cancel_requested/canceled/timed_out to domain JobStatus and v3_jobs; (2) add POST .../aisles/{aid}/jobs/{jid}/cancel or equivalent; (3) persist cancel request (e.g. update job to cancel_requested or set a flag); (4) in V3JobExecutor, before pipeline and optionally between stages, check flag and elapsed time; (5) add timeout config and enforce in executor or worker; (6) update frontend to show new statuses and optionally a cancel button that calls new endpoint.
- **Stage 2/3:** If legacy job flow is removed, document that only v3 job lifecycle applies; otherwise keep both lifecycles documented.
