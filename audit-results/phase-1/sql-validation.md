# Phase 1 — SQL validation notes

## CAS claim (single transaction)

```sql
-- 1) lock + validate job target / terminal status
SELECT target_type, target_id, status
FROM inventory_jobs WITH (UPDLOCK, ROWLOCK)
WHERE id = ?;

-- 2) lock + validate aisle claimable
SELECT status FROM aisles WITH (UPDLOCK, ROWLOCK) WHERE id = ?;

-- 3) job CAS
UPDATE inventory_jobs
SET status = 'running',
    claim_owner_id = ?,
    started_at = COALESCE(started_at, ?),
    last_heartbeat_at = ?,
    current_stage = 'Pipeline',
    current_substep = 'startup_confirmed',
    current_step_started_at = ?,
    updated_at = ?
WHERE id = ?
  AND status = 'starting';

-- 4) aisle (only if job CAS rowcount = 1)
UPDATE aisles
SET status = 'processing', updated_at = ?,
    error_code = NULL, error_message = NULL, retryable = NULL
WHERE id = ?
  AND status IN ('queued', 'assets_uploaded', 'processing');
```

Commit only if both updates succeed. Aisle invalid / rowcount 0 → rollback job claim.

## Stale reclaim (single transaction)

`try_reclaim_stale_job_and_reconcile_aisle`:

1. CAS fail job if still stale (sets `failure_*`, `error_message`, `finished_at`, finalization fields).
2. If CAS lost → rollback / return `won=False`.
3. Update aisle to `FAILED` only when status active **and** `NOT EXISTS` other active job for target (`UPDLOCK`/`HOLDLOCK`).
4. Single commit.

## Batch stale scan

```sql
SELECT TOP (?) id, ...
FROM inventory_jobs
WHERE status IN ('starting','running','cancel_requested')
  AND DATEDIFF(SECOND, COALESCE(last_heartbeat_at, updated_at), ?) >= ?
ORDER BY COALESCE(last_heartbeat_at, updated_at) ASC, id ASC;
```

Default `batch_size=100` (capped at 500). No new index without plan evidence.

## Migrations

Additive: `0071_inventory_jobs_claim_owner_id.sql` — `claim_owner_id VARCHAR(64) NULL`.

Also reflected in `backend/src/database/schema.sql`.

## Unit vs integration evidence

- **Unit** (`test_sql_job_repository.py`): CAS SQL, params, commit/rollback, aisle rowcount 0, target mismatch, exception after job update, stale finalization fields.
- **Integration** (`tests/integration/jobs/test_sql_atomic_job_claim.py`): dual-worker claim, dual recovery stale reclaim, invalid aisle rollback. Skips when SQL Server/ODBC or migration 0071 unavailable; must run in CI with SQL Server before declaring merge-ready on environments without a local DB.

## Isolation

Explicit `SqlServerTransaction` (autocommit=False). No memory fallback on SQL failure.
