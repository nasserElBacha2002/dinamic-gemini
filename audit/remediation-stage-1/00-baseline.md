# Stage 1 — Baseline

| Field | Value |
|-------|-------|
| Branch | `DIN-357` |
| HEAD at start | `5927f18207f5b6784e3dacf0e500bf210003b164` |
| Audit reference commit | `e3a7c0a2933b50f0dcdcce2c42ea0c1411c4cbda` |
| Working tree at start | clean |
| Prior fix evidence | `audit/worker-sql-repository-fix-*.md` → `IMPLEMENTED_WITH_LIMITATIONS` |

## Delta audit → HEAD

`git log --oneline e3a7c0a..HEAD` → `5927f182 updates` (includes prior worker fix already in tree).

## Prior fix vs HEAD (VERIFIED)

Already present before this stage:

- `job_store.claim_next_job` idle-v3 path without ERROR spam
- `worker_runtime.EmbeddedWorkerRuntime` + `/ready` `JOB_WORKER_UNAVAILABLE`
- Startup validates `claim_next_queued_job` when SQL backend resolved
- Unit tests in `test_worker_db_claim.py` / `test_worker_runtime.py`

## Gaps closed in this stage

1. Explicit poll result type `JOB_CLAIMED | IDLE_HEALTHY | CLAIM_UNAVAILABLE`
2. Do not call `_db_repos()` when `LEGACY_STAGE8_SQL_BRIDGE_DISABLED=true`
3. v3 idle remains healthy if optional legacy drain throws (`Invalid object name 'jobs'`)
4. Runtime counters: `recovery_count`, `unexpected_termination_count`, `observability_dict()`
5. Extra unit coverage for the above
