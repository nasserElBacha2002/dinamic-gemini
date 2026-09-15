# Stage-1 corrections — decisions and residual risks

## Status

`CORRECTED_AND_VERIFIED`

## Decisions

1. **Typed claim consumption:** `worker_loop` calls `claim_next_job_cycle()` only. Runtime transitions (`mark_cycle_ok` / `mark_unavailable`) happen in the loop, not in `job_store`.
2. **Legacy bridge policy:** only `DISABLED` (`LEGACY_STAGE8_SQL_BRIDGE_DISABLED=true`) and `DRAIN_REQUIRED` (default). No `BEST_EFFORT`. Under `DRAIN_REQUIRED`, bridge failure after v3 idle is `CLAIM_UNAVAILABLE` (never idle-healthy). Missing `jobs` table is not a feature flag.
3. **Readiness phases:** `STARTING` → first healthy claim/idle → `READY`; `CLAIM_UNAVAILABLE` → `UNAVAILABLE`; `request_stop` → `STOPPING` (503, no unexpected termination counter); unexpected death → `TERMINATED`.
4. **Stale reclaim:** UPDLOCK job row first, then CAS update; deadlock (1205/40001) retries with jitter (max 5); poll interval via `WORKER_STALE_RECLAIM_INTERVAL_SEC` (default 5s).
5. **`claim_next_job()`:** retained as thin legacy wrapper for tests only; documented removal plan. Production worker does not use it.

## Residual risks

- Legacy Stage-8 producers: if any remain in production with bridge disabled, those jobs will not drain. Confirm producers before permanent bridge removal.
- Concurrent reclaim under extreme load may still retry; five successful SQL iterations reduce but do not eliminate theoretical deadlock exhaustion.
- Config alias `LEGACY_STAGE8_SQL_BRIDGE_DISABLED` remains the mode switch (true→DISABLED, false→DRAIN_REQUIRED); retire after cutover ticket, not indefinite.

## Out-of-scope (unchanged)

- AuthZ/BOLA
- Migrations
- Fake `jobs` table creation
- Prompt/LLM paths
- Frontend
