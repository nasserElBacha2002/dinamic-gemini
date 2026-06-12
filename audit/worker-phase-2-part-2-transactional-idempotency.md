# Phase 2 Part 2 — Transactional Idempotent Persistence (Corrections)

## 1. Executive Summary

| Field | Value |
| ----- | ----- |
| **Verdict** | `IMPLEMENTED_WITH_SQL_VALIDATION_BLOCKER` |
| **Strategy** | Delete-and-replace by `(inventory_id, aisle_id, job_id)` inside a transactional Unit of Work |
| **Production files** | `persist_aisle_result.py`, `job_result_unit_of_work.py`, `job_result_scope_store.py`, `job_scoped_recompute.py`, memory/SQL UoW + scope stores, SQL transaction helper, SQL repo `connection=` support, worker/container wiring |
| **Tests added** | `test_worker_phase2_part2_transactional_idempotency.py` (P2-P2-T001–T009), `test_worker_phase2_part2_transactional_idempotency_sql.py` (P2-P2-T010–T012, P2-P2-C013), `test_worker_phase2_part2_corrections.py` (P2-P2-C001–C012) |
| **Memory results** | CONFIRMED_IN_MEMORY — correction + Part 2 + Part 1 + Phase 1 worker suites pass |
| **SQL results** | PENDING_SQL_SERVER_VALIDATION — isolated test DB / ODBC unavailable in sandbox; tests skip safely |
| **Production deployment** | **Not approved** until SQL integration suite passes on an isolated test database |
| **Remaining gaps** | Same-`job_id` concurrent persist locking; failed-job audit retention policy; unique constraints deferred |

## 2. Architecture

### Transaction boundary

`PersistAisleResultUseCase.execute()` validates/maps **before** opening the UoW. Inside one UoW:

1. Delete prior rows for the job scope via `uow.scope_store.delete_scope(...)`
2. Insert positions, products, evidence, raw labels
3. Recompute normalized + final counts for **exact `job_id`** via `JobScopedRecomputeFactory`
4. Commit (or rollback on any exception)

### UnitOfWork contract

`JobResultUnitOfWork` exposes:

- `repositories` — transaction-bound repos
- `scope_store` — `JobResultScopeStore` (count/delete by job scope)
- `commit()` / `rollback()`

No cursor introspection. No optional SQL capability. Factory must be injected explicitly (no memory fallback).

### Scope store port

`JobResultScopeStore` in `application/ports/job_result_scope_store.py`.

Implementations:

- `MemoryJobResultScopeStore` — deletes `entity_type == "position"` evidence only
- `SqlJobResultScopeStore` — same semantics in SQL (`entity_type = 'position'` filter)

`JobResultScopeCleaner` removed; application layer has no raw SQL or `_store` access.

### Recompute contract

`JobScopedRecomputeFactory` / `JobScopedRecompute` — transaction-bound recompute built from UoW repositories. No private `_recompute_uc._normalized_repo` access.

### SQL implementation

`SqlJobResultUnitOfWork` uses `SqlServerClient.begin_transaction()` (public API). One `SqlServerTransaction` connection; UoW owns commit/rollback; transaction object owns connection open/close only.

`sql_repository_cursor` closes cursors in `finally` when using a shared connection.

### Memory implementation

`MemoryJobResultUnitOfWork` snapshots `_store` dicts at `__enter__` and restores on rollback (including delegated repos via `_inner`).

## 3. Before and After Behavior

| Scenario | Before | After |
| -------- | ------ | ----- |
| Same job, same report | Duplicate rows appended | Idempotent replace; stable counts |
| Same job, changed report | Stale rows remain | Stale rows deleted; only new snapshot |
| Failure after deletion | Partial or empty scope | Full rollback to prior snapshot |
| Failure during recompute | Partial domain rows committed | Full rollback |
| New retry job, same aisle | Cross-job mixing possible in `job_scope=all` | Per-job isolation for operational persist/read |
| Failed persist (recompute error) | Partial rows for failed job | No partial rows (transactional rollback) |
| Missing UoW factory | Silent memory fallback | `ValueError` at construction |

## 4. Transaction Scope

**Included:** delete job scope, insert domain snapshot, job-scoped recompute (normalized + final).

**Excluded:** pipeline/LLM calls, artifact upload, `mark_success`, operational_job_id promotion, unrelated aisle/inventory writes.

**Cross-job wording:** Operational persistence and default operational readers are job-scoped. Explicit administrative/analytics scope `"all"` still combines attempts by design.

## 5. Repository Matrix (transaction-bound SQL)

| Repository | Method (persist path) | Shared connection | Internal commit | Covered by test |
| ---------- | --------------------- | ----------------- | --------------- | --------------- |
| SqlPositionRepository | save, list_by_aisle | Yes (`connection=`) | No | P2-P2-C012, T010–T012 |
| SqlProductRecordRepository | save, list_by_position | Yes | No | P2-P2-C012 |
| SqlEvidenceRepository | save, list_by_entity | Yes | No | P2-P2-C007, C013 |
| SqlRawLabelRepository | save, list_for_scope | Yes | No | P2-P2-C012 |
| SqlNormalizedLabelRepository | replace_for_scope, list_for_scope | Yes | No | P2-P2-C012 |
| SqlFinalCountRepository | replace_for_scope, list_for_scope | Yes | No | P2-P2-C012 |
| SqlJobResultScopeStore | delete_scope, count_scope | Yes (cursor on conn) | No | P2-P2-C004, C007, C013 |

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

## 7. Rollback Matrix (evidence labels)

| Failure point | Memory | SQL Server |
| ------------- | ------ | ---------- |
| After job-scope delete | CONFIRMED_IN_MEMORY | PENDING_SQL_SERVER_VALIDATION |
| After first position insert | CONFIRMED_IN_MEMORY | PENDING_SQL_SERVER_VALIDATION |
| After products/evidence | CONFIRMED_IN_MEMORY | PENDING_SQL_SERVER_VALIDATION |
| After raw labels | CONFIRMED_IN_MEMORY | PENDING_SQL_SERVER_VALIDATION |
| During recompute | CONFIRMED_IN_MEMORY | PENDING_SQL_SERVER_VALIDATION |
| Before commit | CONFIRMED_IN_MEMORY | PENDING_SQL_SERVER_VALIDATION |

Memory rollback proven by P2-P2-T004–T006 and correction tests C009–C011. SQL atomicity requires passing T010–T012 and C013 on isolated SQL Server.

## 8. SQL Evidence

| Item | Status |
| ---- | ------ |
| Database isolation | Tests use prefixed UUIDs + `assert_sql_integration_database_is_safe` |
| Tests implemented | P2-P2-T010–T012, P2-P2-C013 |
| Tests executed | **Skipped** without isolated SQL / ODBC in CI sandbox |
| Repeatability | `finally` cleanup + `verify_sql_scope_fully_removed` |
| Cursor lifecycle | CONFIRMED_WITH_FAKE_SQL_RESOURCES (C005, C006) |
| Transaction ownership | CONFIRMED_WITH_FAKE_SQL_RESOURCES (C009–C011) |
| Production wiring | `SqlJobResultUnitOfWorkFactory` via `AppContainer.get_job_result_uow_factory()` → worker |

## 9. Corrections Applied

| # | Issue | Resolution |
| - | ----- | ---------- |
| 1 | Silent memory UoW fallback | Explicit factory required; `ValueError` if missing |
| 2 | `JobResultScopeCleaner` infra coupling | `JobResultScopeStore` port + memory/SQL implementations |
| 3 | Cursor introspection | `scope_store` on UoW contract |
| 4 | Cursor leaks | `sql_repository_cursor` closes in `finally` |
| 5 | Polymorphic evidence delete | `entity_type = 'position'` filter (memory + SQL) |
| 6 | Private recompute access | `JobScopedRecomputeFactory` public contract |
| 7 | Double rollback | UoW owns commit/rollback; transaction owns close only |
| 8 | Private `_connection_string` | `SqlServerClient.begin_transaction()` / `connection_string` property |
| 9 | Shared connection | Transaction-bound repos via `connection=` |
| 10 | Bundle mismatch | `assert_memory_job_result_bundle` / `assert_sql_job_result_bundle` |
| 11 | Broad recompute guard | `_BROAD_RECOMPUTE_SCOPES` rejects `"all"` / `legacy_null` in persist |

## 10. Findings

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

## 11. Remaining Gaps

- SQL Server integration validation on isolated test database (production blocker)
- `operational_job_id` concurrency (last-writer-wins)
- Failed-job historical retention vs transactional rollback distinction
- Unique constraints after data assessment
- Artifact finalization (Phase 3 — out of scope)
- Analytics/admin `job_scope="all"` still available outside persist path

## 12. Recommended Next Step

1. Run P2-P2-T010–T012 and P2-P2-C013 on isolated SQL Server; unblock production approval when green.
2. Continue with operational promotion concurrency and failed-result retention policy.
