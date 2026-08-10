# Phase 1 — Concurrency test report

## Memory contract (`test_phase1_atomic_job_claim.py`)

| Scenario | Expected | Result |
|---|---|---|
| 2 workers, different `claim_owner_id`, same `execution_id` | 1 `ACQUIRED`, 1 `CONFLICT`, 0 `ALREADY_OWNED`, 1 `may_execute` | PASS |
| 8 workers | 1 `ACQUIRED`, 1 `may_execute` | PASS |
| Same owner retry | `ALREADY_OWNED`, attempts/`started_at` unchanged | PASS |
| Null caller / null persisted / both null | `CONFLICT`, `may_execute=False` | PASS |
| Preparation side-effect (2 threads) | 1 continues, 1 halts | PASS |
| 2 stale recovery workers | 1 win | PASS |
| Aisle missing / terminal / mismatch | `TARGET_*`, job remains `STARTING` | PASS |

## SQL unit (`test_sql_job_repository.py`)

CAS SQL + `claim_owner_id` params, commit on dual rowcount=1, rollback on aisle rowcount 0, target mismatch without CAS, exception after job update → rollback, stale finalization fields + commit.

## SQL integration (`test_sql_atomic_job_claim.py`)

Dual connection claim race, dual stale reclaim, invalid aisle leaves job `STARTING`.

**Local run:** skipped when ODBC/SQL Server unavailable (`pytest.skip`). Must execute in CI with SQL Server + migration 0071 applied before merge.

## Strictness

Tests do **not** accept `INVALID_STATUS` or `ALREADY_OWNED` as alternate loser outcomes for different owners. No private method calls.
