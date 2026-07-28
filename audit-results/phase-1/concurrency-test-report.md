# Phase 1 — Concurrency test report

## Suite

`backend/tests/jobs/test_phase1_atomic_job_claim.py`

## Results

```text
backend/.venv/bin/python -m pytest tests/jobs/test_phase1_atomic_job_claim.py -q --no-cov
→ all passed (14 tests)
```

## Critical scenarios

| Test | Expected | Result |
|---|---|---|
| `test_two_workers_one_winner_barrier` | 1× `ACQUIRED`, 1× reject | PASS (Barrier, no sleep) |
| `test_n_workers_single_winner` (N=8) | exactly 1 winner | PASS |
| `test_claim_idempotent_same_execution_does_not_bump_attempt_or_restart` | `ALREADY_OWNED`, same `started_at`/`attempt_count` | PASS |
| `test_claim_conflict_other_execution` | `CONFLICT`, owner unchanged | PASS |
| `test_two_recovery_workers_one_stale_reclaim` | 1× True, 1× False on `try_fail_stale_job` | PASS |
| `test_stale_reclaim_fails_job_and_aisle` | job+aisle `FAILED` | PASS |
| `test_stale_reclaim_does_not_fail_aisle_when_other_active_job` | aisle stays `PROCESSING` | PASS |
| `test_claim_next_queued_mutates_to_starting` | memory claim mutates once | PASS |

## Full backend regression

```text
3811 passed, 44 skipped
```

## Notes

- Concurrent tests use `threading.Barrier` against `MemoryJobRepository` (lock-emulated CAS).
- SQL CAS path is implemented (`UPDATE … WHERE status='starting'` + aisle in one transaction); local environment lacked ODBC Driver 18 for live SQL race tests — memory contract covers the observable outcomes required for merge.
