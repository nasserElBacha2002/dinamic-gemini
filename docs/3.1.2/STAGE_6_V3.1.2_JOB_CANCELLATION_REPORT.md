# STAGE_6_V3.1.2_JOB_CANCELLATION_REPORT.md

## 1. Summary

Stage 6 adds a **cooperative job cancellation mechanism** to the active v3 inventory workflow. The goal is to let operators request cancellation for long-running `process_aisle` jobs, persist and observe cancellation intent, and have the executor honor those requests at safe checkpoints — without force-killing processes or breaking existing v3 contracts.

Implemented changes:
- Extended the v3 `JobStatus` model with **cancellation-related states** (`cancel_requested`, `canceled`, `timed_out`), persisted via `inventory_jobs.status` and exposed through existing status surfaces.
- Added a **v3 cancellation endpoint**: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel`.
- Introduced a `CancelAisleJobUseCase` that validates ownership and updates job status according to a simple, explicit state model.
- Updated `V3JobExecutor` with **cooperative cancellation checkpoints** before pipeline start and after pipeline execution, marking jobs and aisles as canceled when cancellation is observed.
- Kept timeout handling **deferred**; `TIMED_OUT` is reserved for future use, but no automatic timeout policy is enforced in v3.1.2.

Existing v3 APIs and schemas remain backwards compatible; only new status values and a new cancellation route were added.

---

## 2. Job state model

### 2.1 States

The v3 `JobStatus` enum (domain) now includes:

- `queued` — Job has been created and enqueued but not yet started.
- `running` — Job is currently executing the v3 pipeline.
- `cancel_requested` — Operator requested cancellation; job may still be running. Cooperative checkpoints will transition it to `canceled` at the next safe opportunity.
- `canceled` — Job was cooperatively stopped and should not be treated as successful. Partial artifacts may exist but are not considered a final result.
- `timed_out` — **Reserved for future timeout handling** (no behavior implemented in Stage 6).
- `succeeded` — Job completed successfully; final report persisted.
- `failed` — Job failed due to an error; error message persisted.

### 2.2 Transitions (v3.1.2)

- `queued` → `running` — V3JobExecutor starts processing.
- `queued` → `canceled` — Cancel requested **before** execution starts.
- `running` → `cancel_requested` — Cancel requested **during** execution.
- `cancel_requested` → `canceled` — Executor observes `cancel_requested` at a checkpoint and stops before/after major stages.
- `running` → `succeeded` — Pipeline and persist succeeded without cancellation.
- `running` → `failed` — Pipeline or persist failed.
- `queued` / `running` → `failed` — Early validation errors (e.g., missing assets, missing aisle) via `_fail_job_and_aisle`.

Terminal states for Stage 6:
- `succeeded`, `failed`, `canceled`, `timed_out` (though `timed_out` is not yet used).

### 2.3 Cancellation rules

- **Allowed:**
  - `queued` (immediate transition to `canceled`).
  - `running` (transition to `cancel_requested`; later to `canceled`).
- **Idempotent:**
  - `cancel_requested` (repeated cancel calls have no effect).
- **Rejected:**
  - `succeeded`, `failed`, `canceled`, `timed_out` → 409 Conflict.

StartAisleProcessingUseCase now treats jobs in `queued`, `running`, or `cancel_requested` as **active**, blocking new job creation for an aisle until the previous job reaches a terminal state.

---

## 3. API surface

### 3.1 Cancellation endpoint

New v3 endpoint (in `src/api/routes/v3/aisles.py`):

- **Method/Path:** `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/cancel`
- **Status code:** `202 Accepted`
- **Body:** None (callers should continue to poll existing status endpoints).

**Behavior:**
- Validates that the aisle exists and belongs to the given inventory.
- Ensures the job exists, belongs to the aisle, and is a v3 `process_aisle` job.
- Updates job status according to the model in §2.2 via the `CancelAisleJobUseCase`.

**Error mapping:**
- 404 — Aisle does not belong to inventory, or job not found / does not belong to aisle.
- 409 — Cancellation requested for a terminal job (`succeeded`, `failed`, `canceled`, `timed_out`) or a non-`process_aisle` job.

### 3.2 Existing status endpoints

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` (AisleStatusResponse)
  - Continues to expose `latest_job.status` as a string; frontend `JOB_STATUSES` has been extended to include `cancel_requested`, `canceled`, `timed_out`.
- Other v3 routes (inventories, assets, positions, reviews, execution log) are unchanged.

No existing response schemas were structurally modified; only the allowed job status values have been extended.

---

## 4. Execution integration

### 4.1 Ownership of job status changes

- **StartAisleProcessingUseCase:**
  - Creates `Job` with `status=queued` and persists it.
- **V3JobExecutor:**
  - `_mark_running` — sets job to `running` and aisle to `processing`.
  - `_mark_success` — sets job to `succeeded`, stores `result_json` (report path), and sets aisle to `processed`.
  - `_fail_job` / `_fail_job_and_aisle` — set job to `failed` and aisle to `failed` with appropriate error fields.
  - `_cancel_job` / `_cancel_job_and_aisle` (new) — set job to `canceled` and optionally set aisle to `failed` with `error_code='CANCELED'` and `retryable=True`.
- **CancelAisleJobUseCase:**
  - For `queued` jobs: sets `canceled` directly.
  - For `running` jobs: sets `cancel_requested` and leaves the executor to mark `canceled` at a checkpoint.

### 4.2 Cooperative cancellation checkpoints

**Checkpoint 1 — Before pipeline start:**

In `V3JobExecutor.execute`:
- After loading the job:
  - If `status == canceled`: log and return (already canceled).
  - If `status == cancel_requested`: call `_cancel_job(job_id, "Job canceled before execution")` and return.
  - If `status != queued`: log a warning and skip (unchanged behavior for non-queued jobs).

This ensures that cancellation requested **before** execution causes the job to be marked `canceled` without starting the pipeline.

**Checkpoint 2 — After pipeline execution, before persist:**

After `HybridInventoryPipeline.process_video` returns with `code == 0` and before reading/persisting `hybrid_report.json`:
- Reloads current job from `JobRepository`.
- If `status == cancel_requested`:
  - Logs that cancellation was observed.
  - Calls `_cancel_job_and_aisle(job_id, aisle, "Job canceled after pipeline execution")` and returns.

This works as a **cooperative checkpoint** for cancellation requested during execution: the pipeline still runs to completion for this version, but results are not persisted as success; the job and aisle are marked as canceled/failure instead.

**Failure handling:**
- Exceptions or non-zero exit codes still transition jobs to `failed` and aisles to `failed` via `_fail_job_and_aisle`, as before.

### 4.3 Aisle observability

- Aisles cancelled after pipeline execution are marked `FAILED` with `error_code='CANCELED'` and `retryable=True`, making their state visible to existing status consumers without introducing new aisle statuses.
- Aisles for jobs canceled before start remain in their previous state (typically `queued` or `assets_uploaded`), but their `latest_job.status` will be `canceled` via the existing `GetAisleProcessingStatusUseCase` and `ListAislesWithStatusUseCase`.

---

## 5. Persistence changes

### 5.1 Domain and repository

- `src/domain/jobs/entities.py`
  - Extended `JobStatus` enum with `CANCEL_REQUESTED = "cancel_requested"`, `CANCELED = "canceled"`, `TIMED_OUT = "timed_out"`.
- `src/infrastructure/repositories/sql_job_repository.py`
  - No structural changes required; `status` is persisted as a string and deserialized via `JobStatus(status_str)`.
  - New statuses are accepted transparently.

### 5.2 Database schema

- `inventory_jobs.status` remains `VARCHAR(16)` with no CHECK constraint on allowed values; no schema changes were needed.

### 5.3 Frontend types

- `frontend/src/api/types/shared.ts`
  - `JOB_STATUSES` updated to include `'cancel_requested'`, `'canceled'`, `'timed_out'` so the type union matches backend values.
  - No other frontend contract shapes were changed; existing UI uses statuses as strings and treats additional values as supported variants.

---

## 6. Timeout handling

### 6.1 Current decision

- **Timeout is explicitly deferred in Stage 6.**
- The `JobStatus` enum includes `TIMED_OUT` to reserve the state, but no code currently sets it.

### 6.2 Rationale

- Correct cooperative cancellation was prioritized for v3.1.2.
- Implementing timeouts safely would require:
  - Measuring elapsed time from job start (using `created_at`/`updated_at` or an explicit `started_at`).
  - Adding timeout checks at multiple execution boundaries.
  - Defining clear interactions between timeout and manual cancellation, and making sure timeout events are logged and observable.
- Given the current synchronous pipeline and absence of fine-grained progress hooks in the v3 executor, adding a robust timeout policy would risk over-complicating Stage 6.

### 6.3 Compatibility for future timeout work

- `TIMED_OUT` is now part of the domain model and frontend job status union.
- Future work can:
  - Add a configuration key (e.g. `MAX_JOB_DURATION_SECONDS`) to settings.
  - Use `Clock` in `V3JobExecutor` to measure duration and set `TIMED_OUT` at checkpoints.
  - Optionally add execution-log events when timeouts occur.

---

## 7. Risks and deferred items

- **Coarse cancellation checkpoint:**
  - Cancellation requested during pipeline execution only takes effect **after** the pipeline finishes (or fails), at the post-pipeline checkpoint. CPU time is still consumed until the checkpoint. This is acceptable for v3.1.2 but should be documented for operators.
- **Aisle state for pre-start cancellations:**
  - When a queued job is canceled before execution, the aisle status is not automatically changed; only `latest_job.status` reflects `canceled`. This is a conservative choice to avoid conflating cancellation with aisle failure; a future version could introduce a dedicated aisle “canceled” status if desired.
- **No timeouts yet:**
  - Long-running jobs without manual intervention can still run indefinitely. Timeout is a known future requirement (already tracked in Stage 1 findings) but intentionally deferred here.

---

## 8. Validation notes

- **Lifecycle re-audit:**
  - Verified that `JobStatus` is only used in the v3 domain entity and related use cases (`StartAisleProcessingUseCase`, `GetAisleProcessingStatusUseCase`, `V3JobExecutor`, `SqlJobRepository`), and that legacy job status enums (in `src/jobs/models.py`) remain untouched.
  - Confirmed that `ListAislesWithStatusUseCase` and `GetAisleProcessingStatusUseCase` simply surface whatever `JobStatus` string is persisted; they do not enforce a finite set.
- **API compatibility:**
  - No Pydantic schemas were changed; only the allowed `JobStatus` string values expanded.
  - Frontend `JOB_STATUSES` was updated to match backend values; existing UI usage treats them as labels.
- **Cancellation behavior:**
  - By code inspection:
    - Cancel on `queued` → immediate `canceled`, executor short-circuits and never starts the pipeline.
    - Cancel on `running` → `cancel_requested`, executor honors this after the pipeline completes and before persist.
    - Cancel on terminal states → 409 Conflict.
  - Executor correctly skips or cancels jobs already in `canceled` / `cancel_requested` before start.
- **Timeout:**
  - No code references `JobStatus.TIMED_OUT` beyond the enum and documentation. Behavior remains unchanged.

---

**Document version:** 1.0  
**Stage:** 6 — Job cancellation and long-running process control  
**Date:** 2025-03-06
