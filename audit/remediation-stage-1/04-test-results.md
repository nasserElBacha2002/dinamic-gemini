# Stage 1 — Test results

## Focused (required)

```bash
cd backend
.venv/bin/ruff check src/api/server.py src/jobs/job_store.py src/jobs/worker.py \
  src/jobs/worker_runtime.py src/jobs/run_worker.py src/jobs/claim_cycle.py \
  tests/jobs/test_worker_db_claim.py tests/jobs/test_worker_runtime.py \
  tests/api/test_health_ready_repository_backend_phase2.py
# → All checks passed

.venv/bin/mypy src/api/server.py src/jobs/job_store.py src/jobs/worker.py \
  src/jobs/worker_runtime.py src/jobs/run_worker.py src/jobs/claim_cycle.py
# → Success: no issues found in 6 source files

.venv/bin/python -m pytest -q \
  tests/jobs/test_worker_db_claim.py \
  tests/jobs/test_worker_runtime.py \
  tests/jobs/test_run_worker_entrypoint.py \
  tests/api/test_health_ready_repository_backend_phase2.py \
  tests/api/test_schema_guard_readiness.py \
  --override-ini='addopts='
# → 39 passed
```

## Full backend pytest

```bash
.venv/bin/python -m pytest -q --override-ini='addopts='
# → 5267 passed, 4 skipped, 3 failed (then re-run of the 3 → all passed)
```

Failed-then-passed (flaky / environmental, unrelated to claim_cycle logic):

1. `tests/api/test_capture_sessions_sprint2.py::test_open_session_conflict_returns_409`
2. `tests/integration/jobs/test_sql_atomic_job_claim.py::test_sql_stale_reclaim_one_winner`
3. `tests/integration/positions/test_sql_position_merge.py::test_sql_concurrent_overlapping_sets`

## New / updated unit coverage

- v3 idle does not invoke `_db_repos` when legacy disabled
- v3 idle stays healthy when legacy drain raises `Invalid object name 'jobs'`
- v3 job claimed skips legacy
- recovery increments `recovery_count`
- stopping thread does not false-alarm as terminated
- unexpected `claim_next_job` exception → unavailable
- observability dict counters
