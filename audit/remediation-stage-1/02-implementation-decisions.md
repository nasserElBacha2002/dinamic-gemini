# Stage 1 — Implementation decisions

## 1. Typed claim cycle

New module `backend/src/jobs/claim_cycle.py`:

- `WorkerClaimCycleStatus`: `JOB_CLAIMED` | `IDLE_HEALTHY` | `CLAIM_UNAVAILABLE`
- `WorkerClaimCycleResult`

`claim_next_job_cycle()` is the source of truth; `claim_next_job()` returns `.job` for compatibility.

**Why separate from `domain.jobs.claim.JobClaimOutcome`:** that enum models STARTING→RUNNING ownership CAS, not queue polling.

## 2. Idle vs unavailable

| Condition | Status |
|-----------|--------|
| v3 claim returns job | `JOB_CLAIMED` + `mark_cycle_ok` |
| v3 claim returns `None` (SQL mode) | `IDLE_HEALTHY` + `mark_cycle_ok` **before** optional legacy |
| v3 missing claim / exception (SQL mode) | `CLAIM_UNAVAILABLE` + rate-limited ERROR |
| Legacy bridge disabled | `_db_repos` **not** called |
| Legacy drain throws after v3 idle | stay `IDLE_HEALTHY` (log exception) |
| Non-SQL | memory queue preserved |

## 3. Startup / ready

Unchanged structural decision from prior fix (retained):

- SQL backend resolved + cannot build JobRepository → **abort startup**
- Operational claim path failure / dead thread → **`/ready` 503** `JOB_WORKER_UNAVAILABLE`
- `EMBEDDED_WORKER_ENABLED=false` → worker not required locally

## 4. Observability

`EmbeddedWorkerRuntime` now tracks `recovery_count`, `unexpected_termination_count`, and exposes `observability_dict()` (no secrets).

## 5. Out of scope (not done)

- AuthZ/BOLA
- Creating empty `jobs` table
- Remote readiness probe for dedicated worker process
- Migrating FastAPI `on_event` → lifespan
