# v3 Job Lifecycle — Source of Truth and Cancel-State Contract (3.2.5)

**Release**: 3.2.5 — Phase 3 (Job Lifecycle Hardening)  
**Purpose**: Document the authoritative v3 job state source of truth, write/read paths, cancel-state semantics, retry/re-processing boundary, historical reads and artifact dependency, and legacy coexistence. This makes the active v3 lifecycle contract explicit, test-protected, and safe for later phases.

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

## 5. Retry and re-processing boundary

**Allowed / disallowed process-start behavior by latest-job state**

- **QUEUED**, **RUNNING**, **CANCEL_REQUESTED**: `POST .../process` is **blocked**. The use case `StartAisleProcessingUseCase` calls `JobRepository.get_latest_by_target("aisle", aisle_id)` and, if the latest job has one of these statuses, raises `ActiveJobExistsError`. The API returns **409** with a detail message indicating an active job already exists.
- **CANCELED**, **FAILED**, **SUCCEEDED**, **TIMED_OUT**: `POST .../process` is **allowed**. A **new** job is created (new id, QUEUED), enqueued, and saved. This is **re-processing** (starting a new independent job after a terminal state), not “retry” of the same job. The API returns **202** with the new `job_id`.

**API contract for blocked starts**

- When the latest job for the aisle is in a non-terminal state, `POST /api/v3/inventories/{id}/aisles/{id}/process` returns **409 Conflict** with a detail string that includes the existing job status (e.g. “already has an active job (status=queued)”). No new job is created.

**Deferred beyond Phase 3**

- “Retry” as an explicit product concept (e.g. retry the same job id, automatic backoff, or UI “Retry” button semantics) is **not** implemented. Current behavior is: after any terminal state, the client may start a new job via `POST .../process`; that new job is independent. Future retry design (same-job retry, idempotency keys, or dedicated retry endpoint) is out of scope for this phase.

---

## 6. Historical reads and artifact dependency boundary

**What is guaranteed from DB**

- Job state (status, updated_at, error_message, result summary, job id, target_type, target_id, job_type) is stored in **`inventory_jobs`** and read via **`JobRepository`**. List-aisles, aisle-status, and cancel all resolve “latest job” and “job by id” from the repository only. **Lifecycle truth** (current status, latest job per aisle) is **guaranteed** from the DB regardless of filesystem state.

**What is best-effort from filesystem**

- **Execution log** (`GET .../jobs/{job_id}/execution-log`): events are read from `read_execution_log(run_dir)` where `run_dir = output_dir / job_id / RUN_ID`. The file `execution_log.jsonl` is written by the pipeline during execution. Reading it is **best-effort** for traceability and debugging.
- Other artifacts (e.g. `hybrid_report.json`, `input_manifest.json`, pipeline outputs under the job run directory) are **not** used by the active lifecycle API to determine job status. They are used for results, evidence, and debugging.

**What happens when artifacts are missing**

- If the run directory or `execution_log.jsonl` is missing (e.g. job was canceled before run, or files were purged), `read_execution_log(run_dir)` returns an **empty list**. The execution-log endpoint still returns **200** with `events: []`. Job existence and ownership are validated via `JobRepository.get_by_id`; only the event payload is empty.
- **Lifecycle guarantees remain valid**: list-aisles and aisle-status continue to return the job and its status from the repository. Missing execution-log or other artifacts does **not** change job state, latest-job resolution, or cancel semantics. Only traceability/debugging (e.g. viewing the log in the UI) degrades when artifacts are absent.

**Summary**

- DB = authority for job state and latest-job. Filesystem = best-effort for execution log and pipeline artifacts. Missing artifacts affect only traceability/debugging, not lifecycle correctness.

---

## 7. Relationship between DB job state and filesystem artifacts (summary)

- **Job state** (status, updated_at, error_message, result summary) lives in the **database** via `JobRepository` / `inventory_jobs`. This is the authority for “what is the job’s status?” and “what is the latest job for this aisle?”.
- **Filesystem artifacts** (e.g. execution logs, pipeline outputs under the job output directory) are **derived** from the job lifecycle and do **not** replace or override the DB. See §6 for the full historical-read and artifact-dependency boundary.

---

## 8. Legacy fallback coexistence

- The **worker** (`src.jobs.worker`) tries the **v3 path** first (`V3JobExecutor` + v3 `JobRepository`). The legacy path (Stage-7 `JobRecord`, `job_store`) is used only when the v3 path is not applicable (e.g. non–process_aisle or legacy job id).
- **Active v3 semantics** (list, status, cancel, process) must **not** depend on the legacy job store or legacy status enum. Tests and this document exist to keep the v3 read/write path locked to `JobRepository` and domain `JobStatus`, so that later lifecycle work (retry, historical-read) can rely on a single, clear contract.

---

## 9. Open items deferred beyond Phase 3

- **Explicit “retry” product semantics**: Same-job retry, idempotency keys, or a dedicated retry endpoint are not implemented; re-processing after terminal state is the current contract.
- **Historical job list**: Only “latest job per aisle” is exposed; listing all jobs for an aisle or inventory is not in scope.
- **Artifact retention / purge policy**: How long execution logs and pipeline outputs are kept, and behavior when they are purged, is operational/deployment concern; lifecycle guarantees (DB-backed state) hold regardless.
- **Legacy fallback removal**: The worker’s legacy Stage-7 path remains; removal is deferred until v3 is the only job type in use.

---

## References

- Domain: `backend/src/domain/jobs/entities.py`
- Use cases: `start_aisle_processing.py`, `cancel_aisle_job.py`, `list_aisles_with_status.py`, `get_aisle_processing_status.py`
- Executor: `backend/src/infrastructure/pipeline/v3_job_executor.py`
- Repository: `backend/src/infrastructure/repositories/sql_job_repository.py`
- API: `backend/src/api/routes/v3/aisles.py`, `shared.py`
- Audit: `docs/3.2.5/IMPLEMENTATION_AUDIT_3_2_5.md`
