# Phase 2 Part 2 — Transactional Idempotent Persistence

## 1. Executive Summary

| Field | Value |
| ----- | ----- |
| **Verdict** | `PART_2_COMPLETE_WITH_SQL_VALIDATION_PENDING` |
| **Strategy** | Delete-and-replace by `(inventory_id, aisle_id, job_id)` inside a transactional Unit of Work |
| **Production files** | `persist_aisle_result.py`, `job_result_scope_cleaner.py`, `job_result_unit_of_work.py`, memory/SQL UoW, SQL transaction helper, SQL repo `connection=` support, worker/container wiring |
| **Tests added** | `test_worker_phase2_part2_transactional_idempotency.py` (P2-P2-T001–T009), `test_worker_phase2_part2_transactional_idempotency_sql.py` (P2-P2-T010–T012) |
| **Memory results** | 25 passed (Part 2 + Part 1 + Phase 1 worker suites) |
| **SQL results** | 4 skipped — isolated test DB / ODBC driver unavailable in CI sandbox |
| **Remaining gaps** | Same-`job_id` concurrent persist locking; failed-job audit retention policy; unique constraints deferred |

## 2. Architecture

### Transaction boundary

`PersistAisleResultUseCase.execute()` validates/maps **before** opening the UoW. Inside one UoW:

1. Delete prior rows for the job scope (`JobResultScopeCleaner`)
2. Insert positions, products, evidence, raw labels
3. Recompute normalized + final counts for **exact `job_id`**
4. Commit (or rollback on any exception)

### UnitOfWork contract

`JobResultUnitOfWork` / `JobResultUnitOfWorkFactory` in `application/ports/job_result_unit_of_work.py`.

### SQL implementation

`SqlJobResultUnitOfWork` shares one `SqlServerTransaction` and transaction-bound repository instances (`connection=` injection). FK-safe deletes run via cursor in FK order.

### Memory implementation

`MemoryJobResultUnitOfWork` snapshots `_store` dicts at `__enter__` and restores on rollback (including delegated repos via `_inner`).

### Replacement coordinator

`JobResultScopeCleaner.delete_scope()` — explicit `(inventory_id, aisle_id, job_id)`; optional `after_delete_hook` for failure-injection tests.

## 3. Before and After Behavior

| Scenario | Before | After |
| -------- | ------ | ----- |
| Same job, same report | Duplicate rows appended | Idempotent replace; stable counts |
| Same job, changed report | Stale rows remain | Stale rows deleted; only new snapshot |
| Failure after deletion | Partial or empty scope | Full rollback to prior snapshot |
| Failure during recompute | Partial domain rows committed | Full rollback |
| New retry job, same aisle | Cross-job mixing possible in `job_scope=all` | Per-job isolation; operational readers use success job |
| Failed persist (recompute error) | Partial rows for failed job | No partial rows (transactional rollback) |

## 4. Transaction Scope

**Included:** delete job scope, insert domain snapshot, job-scoped recompute (normalized + final).

**Excluded:** pipeline/LLM calls, artifact upload, `mark_success`, operational_job_id promotion, unrelated aisle/inventory writes.

## 5. Repository Changes

| Repository | New method / change | Scope | Transaction-aware? |
| ---------- | ------------------- | ----- | ------------------ |
| All job-result SQL repos | Optional `connection=` ctor | Per-connection | Yes (when in UoW) |
| Scope cleaner | `delete_scope`, `count_scope` | `(inventory_id, aisle_id, job_id)` | Uses UoW cursor (SQL) or memory stores |
| Memory norm/final | `replace_for_scope` (existing) | job_id | Via UoW snapshot |

## 6. Idempotency Matrix

| Layer | Same report twice | Changed report | Cross-job isolation |
| ----- | ----------------- | -------------- | ------------------- |
| Positions | Stable count | Stale removed | Other jobs untouched |
| Products | Stable count | Stale removed | Other jobs untouched |
| Evidence | Stable count | Stale removed | Other jobs untouched |
| Raw labels | Stable count | Stale removed | Other jobs untouched |
| Normalized | Stable count | Stale removed | Other jobs untouched |
| Final counts | Stable count | Stale removed | Other jobs untouched |

Physical row IDs may change on re-persist (delete-and-replace); business snapshot equivalence is preserved.

## 7. Rollback Matrix

| Failure point | Previous snapshot preserved? | Partial rows? | Result |
| ------------- | ---------------------------: | ------------: | ------ |
| After job-scope delete | Yes | No | Rollback |
| After first position insert | Yes | No | Rollback |
| After products/evidence | Yes | No | Rollback |
| After raw labels | Yes | No | Rollback |
| During recompute | Yes | No | Rollback |
| Before commit | Yes | No | Rollback |

## 8. SQL Evidence

| Item | Status |
| ---- | ------ |
| Database isolation | Tests use prefixed UUIDs + `assert_sql_integration_database_is_safe` |
| Tests executed | P2-P2-T010–T012 implemented; **skipped** without isolated SQL |
| Repeatability | `finally` cleanup + `verify_sql_scope_fully_removed` |
| Transaction rollback | Covered by T010 when SQL available |
| Production wiring | `SqlJobResultUnitOfWorkFactory` via `AppContainer.get_job_result_uow_factory()` → worker |

## 9. Findings

### WKR-P2-P2-001

| Field | Value |
| ----- | ----- |
| Severity | Medium |
| Status | Documented |
| Evidence | Concurrent persist for same `job_id` not serialized |
| Current behavior | Last-writer-wins at commit |
| Remaining risk | Rare duplicate work under retry races |
| Recommended next block | Operational promotion concurrency / advisory lock |

### WKR-P2-P2-002

| Field | Value |
| ----- | ----- |
| Severity | Low |
| Status | Accepted |
| Evidence | Failed jobs after transactional rollback leave zero domain rows |
| Current behavior | Job row FAILED; no partial snapshot |
| Remaining risk | Audit may want explicit failed-job retention |
| Recommended next block | Failed-result cleanup and retention policy |

### WKR-P2-P2-003

| Field | Value |
| ----- | ----- |
| Severity | Low |
| Status | Deferred |
| Evidence | No unique constraints on `(job_id, entity_uid)` yet |
| Current behavior | Idempotency via delete-and-replace |
| Remaining risk | Legacy duplicate data if present |
| Recommended next block | Assess duplicates before constraints |

## 10. Remaining Gaps

- `operational_job_id` concurrency (last-writer-wins)
- Failed-job historical retention vs transactional rollback distinction
- Unique constraints after data assessment
- Artifact finalization (Phase 3)
- Analytics/admin `job_scope="all"` still available outside persist path

## 11. Recommended Next Step

Continue with **operational promotion concurrency** and **failed-result retention policy**, then Phase 3 artifact finalization robustness.
