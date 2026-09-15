# Stage 1 — Handoff

## Status

```text
IMPLEMENTED_WITH_LIMITATIONS
```

## Why not `IMPLEMENTED_AND_VERIFIED`

- Full pytest first pass had 3 failures (flaky; pass on isolated re-run).
- SQL stale-reclaim concurrency can still deadlock.
- Dedicated-worker remote readiness is intentionally not invented.

## What reviewers should check first

1. `backend/src/jobs/claim_cycle.py`
2. `backend/src/jobs/job_store.py` (`claim_next_job_cycle`)
3. `backend/src/jobs/worker_runtime.py` (counters + stopping semantics)
4. New tests in `test_worker_db_claim.py` / `test_worker_runtime.py`

## Suggested next stages

- Stage 2+: AuthZ / BOLA (SEC-001/002) — **out of scope here**
- Ops: harden SQL stale reclaim against deadlocks
- Optional: remove Stage-8 bridge after confirming no producers/rows

## Artifacts

See sibling files `00`–`05` and `implementation-stage-1-*.txt` in this directory.
