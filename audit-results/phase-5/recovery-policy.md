# Phase 5 — Recovery policy

## Policy: stale-fail (Phase 3 — unchanged)

1. Detect stale RUNNING/STARTING/CANCEL_REQUESTED (heartbeat/updated older than threshold).
2. CAS `try_reclaim_stale_job_and_reconcile_aisle` → mark FAILED/`STALE_JOB`.
3. Reconcile aisle in the same transactional path.
4. Create a new attempt only via existing retry lineage APIs/policies (not lease steal).
5. Launch worker for the new job when applicable.
6. Record prior attempt via `retry_of_job_id` when present.

## Idempotency

Two recovery processes on the same stale job:

- one CAS winner
- loser observes no change / refreshed row
- at most one FAILED transition from reclaim

## Manual ops

```bash
python -m scripts.ops.inspect_job --job-id <id>
python -m scripts.ops.audit_job_state_consistency --dry-run
python -m scripts.ops.recover_job --job-id <id> --dry-run --actor <ops> --reason '<why>'
python -m scripts.ops.recover_job --job-id <id> --confirm --actor <ops> --reason '<why>'
```

Rules:

- dry-run by default
- refuse recovery when an active (unexpired) lease exists
- actor + reason mandatory
- audit via structured `event=job_recovery_*` logs

## Config

| Env | Default | Notes |
| --- | ------- | ----- |
| RECOVERY_ENABLED | false | Explicit in production |
| RECOVERY_INTERVAL_SEC | 60 | Scheduler interval if enabled |
| RECOVERY_BATCH_SIZE | 20 | Hard cap |
| RECOVERY_MAX_ATTEMPTS | 3 | Lineage cap |
