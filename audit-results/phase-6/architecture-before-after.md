# Phase 6 — Architecture before / after

## Before

- `PersistAisleResult` used `getattr(uow, "fence_job_lease")` for optional fencing.
- Application download gate raised FastAPI `HTTPException`.
- Recovery launch failures detected via string/getattr matching.
- Job/aisle consistency auditor used `Any` + getattr duck typing.
- SQL job row mapping and lease CAS predicates lived inline in `SqlJobRepository` / UoW.
- No architecture tests for application→FastAPI or domain→infrastructure imports.

## After

- `JobResultUnitOfWork.fence_job_lease(...) -> bool` is part of the Protocol.
  - SQL: UPDLOCK fence, returns `True`.
  - Memory: asserts when `job_repo` bound (`True`); unbound returns `False`.
  - Persist asserts via `_job_repo` only when UoW returns `False` (no double fence on SQL).
- Download capacity errors are application-typed; API maps to HTTP 503.
- `WorkerLaunchFailedError` / `DownloadCapacityExceededError` in `application/errors.py`.
- Shared `sql_job_row_mapper` + `sql_job_lease_predicates`.
- Architecture + characterization tests under `backend/tests/architecture/`.

## Unchanged (deferred)

- `AppContainer` still the composition root (~1700+ LOC); no Service Locator split.
- `V3JobExecutor` still hosts large CODE_SCAN/OCR path methods (out of Phase 6 scope).
- `V3JobFinalizationService` internal structure unchanged.
- Frontend / mobile not modified.
