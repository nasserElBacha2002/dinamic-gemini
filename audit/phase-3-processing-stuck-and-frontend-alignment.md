# Phase 3 — Stuck processing bug and frontend alignment

## Root cause

Production jobs completed the provider pipeline but remained in `PROCESSING` because `SqlJobResultUnitOfWork.__enter__` referenced `SqlJobResultScopeStore` without importing it (`NameError`). Domain persistence never committed; aisle status stayed `processing` while the UI derived activity from aisle status rather than terminal job status.

## SQL UoW correction

Added import in `sql_job_result_unit_of_work.py`. Smoke test asserts `scope_store` and `finalization_evidence` are non-null inside an active UoW.

## Failure terminalization guarantees

`V3JobExecutor` already routes persistence failures through `fail_finalization_and_aisle` with `DOMAIN_PERSISTENCE_FAILED`. Critical logging now includes `aisle_id` and explicitly states `failure_state_persisted=false` when job metadata reporting fails.

## Stale-job reconciliation

`JobStaleReconciler` now sets `finalization_status=failed` when applicable and reconciles aisle `processing/queued` → `failed` via optional `aisle_repo` (wired in API dependencies).

## Event naming correction

Pipeline completion event renamed to `provider_pipeline.completed`. Frontend terminal log parsing accepts legacy `job.succeeded`.

## Recovery lease strategy

SQL store uses `UPDLOCK, HOLDLOCK` on active lease probe + insert in one cursor scope. Memory store remains process-local.

## Resume lease ownership

`RecoveryExecutionContext` on `RecoveryCommand` exempts child operations from acquiring leases; `ResumeJobFinalizationUseCase` holds one parent lease for the coordinated flow.

## Attempt status mapping

Centralized in `map_recovery_outcome_to_attempt_status` — `NOT_ELIGIBLE` → `REJECTED` (not `FAILED`).

## Frontend terminal-state derivation

`deriveEffectiveJobDisplayState` prioritizes latest job terminal status over aisle status. Inventory rows and observability workspace use finalization-aware labels.

## Polling behavior

Job detail polling stops on terminal job status; bounded refresh remains for post-success reconciliation (max 120s).

## Admin recovery UI

`AdminFinalizationRecoveryPanel` on observability workspace (admin only): dry-run before mutation, assessment display, blocked states for `failed_before_domain_commit` / `inconsistent`.

## Tests

Backend: 77 tests in required suites + mapping/stale/auth tests. Frontend: `deriveJobDisplayState.test.ts`. SQL integration for recovery lease concurrency remains environment-dependent.

## Scenario matrix

| Scenario | Job status | Aisle state | Frontend display | Allowed action |
| --- | --- | --- | --- | --- |
| Provider running | RUNNING | PROCESSING | Procesando | Cancel |
| Persisting | RUNNING | PROCESSING | Guardando resultados | None |
| Persistence failure | FAILED | FAILED | Error al guardar resultados | Full retry |
| Artifact failure | FAILED | FAILED | Artefactos incompletos | Admin recovery |
| Technical success, reconciliation failed | SUCCEEDED | partial/processed | Reconciliación pendiente | Admin recovery |
| Stale worker | FAILED | FAILED | Procesamiento interrumpido | Full retry or verify |
| Complete | SUCCEEDED | PROCESSED | Completado | None |

## Remaining limitations

- No automatic recovery scheduler or background retry workers
- SQL integration tests for lease concurrency require SQL Server in CI
- Full frontend test matrix (14 cases) partially covered; extend in follow-up
- Existing stuck jobs with no domain commit must be marked failed manually and retried with a new job id
