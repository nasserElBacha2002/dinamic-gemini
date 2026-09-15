# Stage 1 — Runtime flow before this stage’s delta

## Authoritative v3 path (VERIFIED)

| Concern | Implementation |
|---------|----------------|
| Repo | `AppContainer.get_job_repo()` → `SqlJobRepository` |
| Table | `inventory_jobs` |
| Atomic claim | `SqlJobRepository.claim_next_queued_job()` (+ leases/CAS elsewhere) |
| Stale reclaim | `reclaim_stale_running_jobs` when `worker_stale_running_timeout_sec > 0` |

## Legacy Stage-8 bridge (VERIFIED)

| Concern | Implementation |
|---------|----------------|
| Flag | `LEGACY_STAGE8_SQL_BRIDGE_DISABLED` → `legacy_stage8_sql_bridge_disabled` |
| Builder | `job_store._db_repos()` → `JobsRepository` on table `jobs` |
| When built | SQL enabled + CS present + bridge **not** disabled |

## Worker entrypoints

- Embedded: FastAPI `start_worker` → thread `dinamic-embedded-worker` → `worker_loop`
- Dedicated: `python -m src.jobs.run_worker` (no local thread required for `/ready`)

## `/health` vs `/ready` (before stage delta)

- `/health`: liveness `ok=True` always
- `/ready`: schema + repository backend + embedded worker `readiness_problem()` when required

## Pre-delta claim bug residual

When v3 returned idle **and** legacy bridge was still enabled, a failing legacy `claim_next_queued_job` returned `None` **without** `mark_cycle_ok`, so a prior unavailable state might not recover and idle was ambiguous.

`_db_repos()` was still invoked even when the bridge flag was disabled (early-return inside the helper), which the Stage 1 contract asked to avoid.
