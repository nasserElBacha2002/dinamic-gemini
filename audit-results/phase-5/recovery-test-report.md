# Phase 5 — Recovery test report

## Memory

| Case | Result |
| ---- | ------ |
| Recover creates child + one worker launch | PASS |
| Two concurrent recoverers → one child, one launch | PASS |
| Max attempts / active lease | PASS |
| Dry-run / worker launch failure → `WORKER_LAUNCH_FAILED` | PASS |
| Correlation preserved on child payload | PASS |

Suite: `backend/tests/observability/test_recover_stale_job.py`

## SQL (real)

| Case | Result |
| ---- | ------ |
| Two concurrent recoverers → one retry + one worker | PASS (deadlock → `LOST_CAS`) |
| Lineage `retry_of_job_id` + correlation | PASS |

Suite: `backend/tests/integration/recovery/test_sql_recover_stale_job.py`  
Requires SQL Server + `retry_of_job_id` column (migrations incl. `0073`).

## Notes

Mocks are not the sole evidence for SQL recovery. Memory unique constraint mirrors SQL filtered unique index for concurrent create races.
