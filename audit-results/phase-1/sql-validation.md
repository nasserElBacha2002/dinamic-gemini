# Phase 1 — SQL validation notes

## CAS claim

```sql
UPDATE inventory_jobs
SET status = 'running',
    started_at = COALESCE(started_at, ?),
    last_heartbeat_at = ?,
    current_stage = 'Pipeline',
    current_substep = 'startup_confirmed',
    current_step_started_at = ?,
    updated_at = ?
WHERE id = ?
  AND status = 'starting';
```

Success: `@@ROWCOUNT == 1` (pyodbc `cursor.rowcount`).

Aisle (same transaction):

```sql
UPDATE aisles
SET status = 'processing', updated_at = ?,
    error_code = NULL, error_message = NULL, retryable = NULL
WHERE id = ?
  AND status IN ('queued', 'assets_uploaded', 'processing');
```

## Stale fail (per job)

```sql
UPDATE inventory_jobs
SET status = 'failed', ...
WHERE id = ?
  AND status IN ('starting', 'running', 'cancel_requested')
  AND DATEDIFF(SECOND, COALESCE(last_heartbeat_at, updated_at), ?) >= ?;
```

Then aisle reconcile only if no other active job for `target_id`.

## Migrations

**None.** Reuses `execution_id`, `last_heartbeat_at`, `attempt_count`, `started_at` from existing schema (`0006_add_inventory_job_runtime_metadata.sql` et al.).

## Indexes

No new indexes. Claim is by primary key `id`. Stale scan uses `status` + heartbeat; acceptable for Phase 1 volume; revisit if reclaim latency grows.

## Isolation

Claim uses an explicit `SqlServerTransaction` (autocommit=False) spanning job+aisle updates; commit only after both statements succeed.
