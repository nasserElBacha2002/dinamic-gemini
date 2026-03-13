# AUDIT_STAGE_6_JOB_CANCELLATION.md

## 1. Verdict

**Approved with observations**

## 2. Summary

The Stage 6 implementation adds cooperative job cancellation to the v3 process_aisle flow with a clear state model, a focused cancellation endpoint, and executor checkpoints that prevent canceled jobs from later reporting success. Status changes are consistently modeled across domain, repository, API, and frontend types. Timeout handling is correctly deferred but prepared for via a reserved `timed_out` status. Remaining observations are mostly about coarse-grained checkpoints and aisle state signaling, not correctness defects.

## 3. What was reviewed

- **Domain / model**
  - `src/domain/jobs/entities.py` (JobStatus enum and Job dataclass)
- **Use cases / application**
  - `src/application/use_cases/start_aisle_processing.py`
  - `src/application/use_cases/get_aisle_processing_status.py`
  - `src/application/use_cases/cancel_aisle_job.py`
- **Infrastructure / execution**
  - `src/infrastructure/repositories/sql_job_repository.py`
  - `src/infrastructure/pipeline/v3_job_executor.py`
  - `src/jobs/worker.py` (to confirm v3 vs legacy separation)
- **API layer**
  - `src/api/routes/v3/aisles.py`
  - `src/api/dependencies.py`
- **Frontend**
  - `frontend/src/api/types/shared.ts`
  - `frontend/src/api/types/responses.ts`
- **Documentation**
  - `docs/3.1.2/STAGE_6_V3.1.2_JOB_CANCELLATION_REPORT.md`

## 4. Findings

### 4.1 State model correctness

- **Finding S1 (Low)**  
  **Severity:** Low  
  **Explanation:** The extended `JobStatus` enum (`queued`, `running`, `cancel_requested`, `canceled`, `timed_out`, `succeeded`, `failed`) is coherent and consistently used in the v3 job flow. New values are introduced only in the domain enum and are persisted as raw strings via `SqlJobRepository`, which already supports arbitrary status strings.  
  **Evidence:**  
  - `src/domain/jobs/entities.py`:
    ```python
    class JobStatus(str, Enum):
        QUEUED = "queued"
        RUNNING = "running"
        CANCEL_REQUESTED = "cancel_requested"
        CANCELED = "canceled"
        TIMED_OUT = "timed_out"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
    ```  
  - `sql_job_repository.py` uses `job.status.value` for persistence and `JobStatus(status_str)` for loading; no special-casing of specific values.

- **Finding S2 (Medium)**  
  **Severity:** Medium  
  **Explanation:** Valid and invalid transitions are encoded in one place (`CancelAisleJobUseCase`) and partially in `V3JobExecutor`. The rules are simple and explicit:  
  - `queued` → `canceled` (via cancel use case).  
  - `running` → `cancel_requested` (via cancel use case) → `canceled` (via executor checkpoint).  
  - `cancel_requested` → no-op for further cancellation requests.  
  - Terminal states (`succeeded`, `failed`, `canceled`, `timed_out`) reject cancellation.  
  This aligns with the described model and avoids implicit transitions scattered across the codebase.  
  **Evidence:**  
  - `cancel_aisle_job.py` checks status and:
    - For `QUEUED`: sets `CANCELED` and persists.  
    - For `RUNNING`: sets `CANCEL_REQUESTED`.  
    - For `CANCEL_REQUESTED`: returns early (idempotent).  
    - For `SUCCEEDED`, `FAILED`, `CANCELED`, `TIMED_OUT`: raises `ValueError`.  
  - `V3JobExecutor.execute`:
    - Treats `CANCELED` as a no-op before start.  
    - Treats `CANCEL_REQUESTED` before start as “cancel before execution” (calls `_cancel_job`).  
    - After successful pipeline run, reloads job and if `CANCEL_REQUESTED` calls `_cancel_job_and_aisle`.  

- **Finding S3 (Low)**  
  **Severity:** Low  
  **Explanation:** `TIMED_OUT` is safely **reserved**: it appears only in `JobStatus` and in the set of terminal statuses that block cancellation; no code currently transitions into `TIMED_OUT` or assumes timeouts are implemented.  
  **Evidence:**  
  - Grep shows `TIMED_OUT` only in `domain/jobs/entities.py`, docs, and type unions; no executor or use case sets it.  

### 4.2 API semantics

- **Finding A1 (Low)**  
  **Severity:** Low  
  **Explanation:** The cancellation endpoint validates ownership and distinguishes between not-found, conflict, and accepted states. It correctly delegates business logic to the use case and maps exceptions to HTTP codes.  
  **Evidence:**  
  - `aisles.py` `cancel_aisle_job` route:
    - Uses `CancelAisleJobUseCase` via `get_cancel_aisle_job_use_case`.  
    - On `AisleNotFoundError` → 404 with generic message about inventory/aisle/job mismatch.  
    - On `ValueError` (terminal / invalid state) → 409.  
    - Returns 202 for successful cancellation request (including pre-start immediate cancel).  
  - `CancelAisleJobUseCase` ensures:
    - Aisle belongs to inventory.  
    - Job exists, is `target_type='aisle'`, `target_id=aisle_id`, and `job_type='process_aisle'`.  

- **Finding A2 (Low)**  
  **Severity:** Low  
  **Explanation:** The endpoint does not misrepresent cancellation: for `running` jobs it only sets `cancel_requested` and returns 202; it does not report that the job is already canceled. Callers must continue to poll status via existing endpoints.  
  **Evidence:**  
  - `CancelAisleJobUseCase` for `RUNNING` only updates `job.status = JobStatus.CANCEL_REQUESTED`.  
  - No route or use case sets `CANCELED` directly for running jobs; that responsibility lies in the executor checkpoint.  

### 4.3 Executor behavior

- **Finding E1 (Medium)**  
  **Severity:** Medium  
  **Explanation:** Executor entry-point checks job status and cooperatively handles pre-start cancellation cases without starting the pipeline:  
  - `None` or non-`process_aisle` → returns False (legacy path).  
  - `CANCELED` → logs and returns True (already canceled, nothing to do).  
  - `CANCEL_REQUESTED` → `_cancel_job(job_id, "Job canceled before execution")` and returns True.  
  - Only `QUEUED` jobs proceed; others are logged and skipped.  
  This is safe and aligns with the intent to avoid work for already canceled jobs.  
  **Evidence:**  
  - `V3JobExecutor.execute` early checks on `job.status` with the above branches.  

- **Finding E2 (Medium)**  
  **Severity:** Medium  
  **Explanation:** Executor post-pipeline checkpoint correctly prevents canceled-running jobs from later becoming `SUCCEEDED`. After `process_video` returns with `code == 0`, the executor reloads the job and, if status is `CANCEL_REQUESTED`, calls `_cancel_job_and_aisle` and returns before report persist or success marking. This ensures that manual cancellation during execution will ultimately surface as `canceled` (job) and `failed/CANCELED` (aisle).  
  **Evidence:**  
  - After successful pipeline call, before reading `hybrid_report.json`, code re-fetches job:  
    ```python
    current_job = self._job_repo.get_by_id(job_id)
    if current_job is not None and current_job.status == JobStatus.CANCEL_REQUESTED:
        self._cancel_job_and_aisle(job_id, aisle, "Job canceled after pipeline execution")
        return True
    ```  
  - `_cancel_job_and_aisle` sets job `CANCELED` and aisle `FAILED` with `error_code="CANCELED"`.  

- **Finding E3 (Low)**  
  **Severity:** Low  
  **Explanation:** Failure paths are clearly distinct from cancellation paths. Exceptions or non-zero pipeline exit codes still go through `_fail_job_and_aisle`, leaving `FAILED` as the final state; there is no path where cancellation erroneously transitions into `SUCCEEDED`.  
  **Evidence:**  
  - For `code != 0`, executor reads `read_last_stage_error`, then calls `_fail_job_and_aisle` and returns.  
  - Outer `except Exception as e:` also calls `_fail_job_and_aisle`.  
  - `_mark_success` is only called after the checkpoint where cancellation is checked; if `CANCEL_REQUESTED` is set, `_mark_success` is not reached.  

- **Finding E4 (Low)**  
  **Severity:** Low  
  **Explanation:** Cooperative cancellation is **coarse-grained**: a running job only respects cancellation after the pipeline finishes, not mid-stage. This is consistent with the implementation goals for v3.1.2 and correctly documented as a limitation, not a bug.  
  **Evidence:**  
  - No additional cancellation checks inside pipeline stages; only before and after `process_video`.  
  - Stage 6 report explicitly calls out that cancellation requested during execution only takes effect at the post-pipeline checkpoint.  

### 4.4 State consistency (aisle/job)

- **Finding C1 (Medium)**  
  **Severity:** Medium  
  **Explanation:** When cancellation is observed **after pipeline execution**, aisle state is forced to `FAILED` with `error_code="CANCELED"` and `retryable=True`, while job state becomes `CANCELED`. This means “canceled after having done work” is surfaced to existing aisle status consumers as a failure-with-cancel code, which is a reasonable compromise given that no dedicated `AISLE_STATUS=CANCELED` exists.  
  **Evidence:**  
  - `_cancel_job_and_aisle` calls:  
    ```python
    aisle.mark_failed(now, error_code="CANCELED", error_message=reason, retryable=True)
    ```  
  - Aisle status enum in `domain/aisle/entities.py` has no `CANCELED`; failure is the only error-like terminal state.  

- **Finding C2 (Low)**  
  **Severity:** Low  
  **Explanation:** When a `QUEUED` job is canceled before execution, only the job is updated to `CANCELED`; aisle state is not automatically changed (it remains `QUEUED` or `ASSETS_UPLOADED` etc.). This avoids conflating “canceled before start” with a failure but means the aisle’s own status does not explicitly mention cancellation. Latest job status (`CANCELED`) is still visible via `GetAisleProcessingStatusUseCase`.  
  **Evidence:**  
  - `CancelAisleJobUseCase` only updates the job in the `QUEUED` branch; it does not touch the aisle.  
  - `GetAisleProcessingStatusUseCase` continues to surface `latest_job` from `JobRepository`.  

### 4.5 Frontend compatibility

- **Finding F1 (Low)**  
  **Severity:** Low  
  **Explanation:** Extending `JOB_STATUSES` to include the new statuses is sufficient for type compatibility. The frontend currently treats status values as opaque strings (used in summaries and UI mapping), and new values will render as distinct states without breaking existing logic. There is no hard-coded assumption in TS code that only the original four statuses exist.  
  **Evidence:**  
  - `frontend/src/api/types/shared.ts` now:  
    ```ts
    export const JOB_STATUSES = [
      'queued',
      'running',
      'cancel_requested',
      'canceled',
      'timed_out',
      'succeeded',
      'failed',
    ] as const;
    ```  
  - `AisleJobSummary` and `JobSummary` use `JobStatus | string`; status values are typically mapped for display, not for branching on a fixed set.  
  - No grep evidence of strict equality checks against only the original four values in frontend code.  

### 4.6 Documentation / report accuracy

- **Finding D1 (Low)**  
  **Severity:** Low  
  **Explanation:** `STAGE_6_V3.1.2_JOB_CANCELLATION_REPORT.md` accurately reflects the actual implementation. It describes the state model, the endpoint, the executor checkpoints, the aisle behavior on cancellation, and the timeout deferral. It clearly distinguishes between cancellation requested vs completed and explicitly notes that timeouts are not implemented yet.  
  **Evidence:**  
  - Report §2 matches the enum and `CancelAisleJobUseCase` logic.  
  - Report §3 describes the exact new endpoint path and its behavior.  
  - Report §4 explains pre- and post-pipeline checkpoints as implemented.  
  - Report §6 states timeout is deferred and `TIMED_OUT` is reserved only.  

## 5. Positive notes

- Cancellation is implemented as a **cooperative, best-effort protocol**, not as hard process killing, which is appropriate for this pipeline-heavy system.
- The **state model is simple and explicit**, with cancellation logic concentrated in `CancelAisleJobUseCase` and `V3JobExecutor`, reducing the risk of scattered, inconsistent handling.
- The API design (202 for accepted, 409 for conflicts, 404 for ownership issues) is clear and predictable for operators.
- Existing v3 contracts were **not broken**: only status value sets were extended, and a new endpoint was added in a coherent location.
- Timeout support was **properly deferred**, but the design leaves a clear path for adding it later.

## 6. Risks or gaps

- **Coarse checkpoints:** Cancellation requested during execution only takes effect after the pipeline finishes its current run. This means resource usage is not reduced for that run; cancellation is primarily about final state and observability rather than early termination. This is acceptable for v3.1.2 but should be communicated to operators.
- **Aisle “canceled” semantics:** Using `FAILED` + `error_code="CANCELED"` to represent canceled aisles may be slightly confusing if the UI or operators treat all failures the same. However, this is consistent with the existing aisle state machine and avoids introducing a new aisle status in this stage.
- **Stuck `cancel_requested` jobs:** If the executor never runs for a job (e.g., worker is down), `cancel_requested` may remain for some time. The gating logic prevents a new job from starting while this status is in place. This is inherent to cooperative cancellation and can be mitigated operationally (e.g., by ensuring workers run) or with future timeout/cleanup features.

## 7. Recommended follow-ups

All recommendations are **non-blocking** and can be addressed in future iterations:

- Consider adding **operator-facing documentation** (ops runbook) clarifying that:
  - Cancellation during execution becomes visible only after the current pipeline run completes.
  - Aisle failures with `error_code="CANCELED"` represent cooperative cancellations, not technical errors.
- In a future version, evaluate whether introducing an explicit **`AISLE_STATUS=CANCELED`** state would improve clarity vs overloading `FAILED`.
- When introducing timeout handling, reuse the existing `TIMED_OUT` status and the executor checkpoints, and ensure interactions with `CANCEL_REQUESTED` are clearly defined.

## 8. Final recommendation

Stage 6 **job cancellation and long-running process control** is **approved with observations**. The implementation is correct, coherent with the rest of the v3 architecture, and proportionate to v3.1.2 goals. No blocking lifecycle, API, or compatibility issues were found; remaining concerns are around operational clarity and future extensibility, not correctness.  

