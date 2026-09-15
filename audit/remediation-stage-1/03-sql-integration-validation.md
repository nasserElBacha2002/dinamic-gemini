# Stage 1 — SQL integration validation

## Environment

| Item | Value |
|------|-------|
| `sqlserver_enabled` | true |
| Resolve mode | `split_env` |
| Target | `localhost` |
| DB used by tests | `dinamic_inventory_test` (per ODBC errors) |

## Commands

```bash
cd backend
.venv/bin/python -m pytest -q \
  tests/integration/jobs/test_sql_atomic_job_claim.py::test_sql_concurrent_claim_one_winner \
  --override-ini='addopts='

.venv/bin/python -m pytest -q \
  tests/integration/jobs/test_sql_atomic_job_claim.py \
  tests/integration/jobs/test_sql_job_lease_fencing.py \
  --override-ini='addopts='
```

## Results

| Test / suite | Result |
|--------------|--------|
| `test_sql_concurrent_claim_one_winner` | **PASSED** (two workers / one ACQUIRED) |
| `test_sql_atomic_job_claim` + lease fencing suite | **7 passed, 1 failed** |
| `test_sql_stale_reclaim_one_winner` | **FAILED** intermittently — SQL deadlock `40001` on reclaim (pre-existing concurrency hazard; not introduced by claim_cycle changes) |

## What this proves

- Atomic claim uniqueness on SQL Server for the v3 ownership path is still enforced (`concurrent_claim_one_winner`).
- Stale reclaim under contention can deadlock in this DB; not accepted as Stage 1 green for that scenario.

## What was not re-proven here

- End-to-end embedded `worker_loop` + `claim_next_job_cycle` against live empty `inventory_jobs` in Docker DEV (inferred from unit + SQL repo tests).
- Legacy bridge enabled with a compatible `jobs` schema drain (bridge left optional; default drain skipped when disabled).
