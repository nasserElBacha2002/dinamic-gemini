# v3 Job Lifecycle — Source of Truth and Cancel-State Contract (3.2.5)

**Release**: 3.2.5 — Phase 3 Block 1  
**Purpose**: Document the authoritative v3 job state source of truth, write/read paths, cancel-state semantics, and the relationship between DB state and filesystem artifacts. This makes the active v3 lifecycle contract explicit and safe for later lifecycle work (retry, historical-read hardening).

---

## 1. Source of truth for v3 job state

- **Authority**: The **v3 job state** is the **domain entity** `Job` (`src.domain.jobs.entities`) with **status** from `JobStatus` in the same module (`QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELED`, `TIMED_OUT`, `SUCCEEDED`, `FAILED`).
- **Persistence**: The single source of truth for *persisted* v3 job state is the **`JobRepository`** contract and its production implementation **`SqlJobRepository`** (`backend/src/infrastructure/repositories/sql_job_repository.py`), which reads/writes the **`inventory_jobs`** table.
- **Legacy**: The legacy Stage-7 job store (`src.jobs.models.JobStatus`, `JobRecord`, `job_store`) is **not** the source of truth for v3 API behavior. The active v3 API and v3 executor must **not** depend on it for reading or writing job state. Coexistence is for backward compatibility of the legacy worker path only.

---

## 2. Write path (who writes state transitions)

- **Start processing**: `StartAisleProcessingUseCase` (`src.application.use_cases.start_aisle_processing`) creates a new `Job` in `QUEUED` and saves it via `JobRepository.save`.
- **Cancel request**: `CancelAisleJobUseCase` (`src.application.use_cases.cancel_aisle_job`) loads the job via `JobRepository.get_by_id`, applies cancel semantics (see below), and saves via `JobRepository.save`.
- **Execution**: `V3JobExecutor` (`src.infrastructure.pipeline.v3_job_executor`) is the only component that transitions jobs from `QUEUED` → `RUNNING` and to terminal states (`SUCCEEDED`, `FAILED`, `CANCELED`, `TIMED_OUT`). It loads the job with `JobRepository.get_by_id`, updates status/updated_at/error_message/result fields, and saves with `JobRepository.save`. It also observes `CANCEL_REQUESTED` and transitions to `CANCELED` at safe points (before starting the pipeline or after the pipeline run).

No other code path should mutate v3 job state for the active API. Legacy worker paths that use `job_store` / `JobRecord` do **not** write to the same authority used by v3 list/status/cancel; they remain separate.

---

## 3. Read path (who reads state)

- **Aisle list**: `ListAislesWithStatusUseCase` uses `JobRepository.get_latest_by_targets(target_type="aisle", target_ids=...)` to obtain the latest job per aisle. The API builds the response from domain `Job` (e.g. `latest_job.status.value` → `"canceled"` / `"cancel_requested"`).
- **Aisle status**: `GetAisleProcessingStatusUseCase` uses `JobRepository.get_latest_by_target(target_type="aisle", target_id=...)` and returns the same shape.
- **Cancel endpoint**: The cancel handler loads the job implicitly via `CancelAisleJobUseCase`, which uses `JobRepository.get_by_id`.
- **Execution log**: The execution-log endpoint uses `JobRepository.get_by_id` to validate the job and then reads filesystem artifacts for the log; job state itself comes from the repository.

All of these read from **`JobRepository`** and **domain `Job`/`JobStatus`** only. They do **not** read from Stage-7 `JobRecord` or `src.jobs.models.JobStatus`.

---

## 4. Cancel-state transitions

- **QUEUED → CANCELED**: Cancel use case marks the job `CANCELED` immediately (job never started) and saves.
- **RUNNING → CANCEL_REQUESTED**: Cancel use case marks the job `CANCEL_REQUESTED` and saves; the executor observes this and transitions to `CANCELED` at the next safe point (before start or after pipeline).
- **CANCEL_REQUESTED → CANCEL_REQUESTED**: Idempotent; no error, no state change.
- **Terminal** (`SUCCEEDED`, `FAILED`, `CANCELED`, `TIMED_OUT`): Cancel use case raises `ValueError`; API returns 409. No invalid transition.

Cancel states are **not** flattened into generic failed/succeeded semantics; `cancel_requested` and `canceled` are first-class and exposed in list/status responses as `latest_job.status` values.

---

## 5. Relationship between DB job state and filesystem artifacts

- **Job state** (status, updated_at, error_message, result summary) lives in the **database** via `JobRepository` / `inventory_jobs`. This is the authority for “what is the job’s status?” and “what is the latest job for this aisle?”.
- **Filesystem artifacts** (e.g. execution logs, pipeline outputs under the job output directory) are **derived** from the job lifecycle (e.g. created when the executor runs). They do **not** replace or override the DB as the source of truth for job state. Reading artifacts (e.g. execution log) is for traceability and debugging; the API still resolves “current job status” from the repository.

---

## 6. Legacy fallback coexistence

- The **worker** (`src.jobs.worker`) tries the **v3 path** first (`V3JobExecutor` + v3 `JobRepository`). The legacy path (Stage-7 `JobRecord`, `job_store`) is used only when the v3 path is not applicable (e.g. non–process_aisle or legacy job id).
- **Active v3 semantics** (list, status, cancel, process) must **not** depend on the legacy job store or legacy status enum. Tests and this document exist to keep the v3 read/write path locked to `JobRepository` and domain `JobStatus`, so that later lifecycle work (retry, historical-read) can rely on a single, clear contract.

---

## 7. References

- Domain: `backend/src/domain/jobs/entities.py`
- Use cases: `start_aisle_processing.py`, `cancel_aisle_job.py`, `list_aisles_with_status.py`, `get_aisle_processing_status.py`
- Executor: `backend/src/infrastructure/pipeline/v3_job_executor.py`
- Repository: `backend/src/infrastructure/repositories/sql_job_repository.py`
- API: `backend/src/api/routes/v3/aisles.py`, `shared.py`
- Audit: `docs/3.2.5/IMPLEMENTATION_AUDIT_3_2_5.md`
