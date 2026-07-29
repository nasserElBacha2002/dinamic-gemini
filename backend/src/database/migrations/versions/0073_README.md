# Migration 0073 — `UX_inventory_jobs_retry_of_job_id`

Enforces at most one child job per `retry_of_job_id` (idempotent recovery).

## Preflight (required)

Before applying migration 0073 on a database that may already contain recovery retries:

```bash
python -m scripts.ops.preflight_0073_retry_of_duplicates
```

Exit code `0` = no duplicate groups. Non-zero = duplicates exist; **resolve manually** before re-running migration.

## Duplicate resolution (manual)

When multiple rows share the same `retry_of_job_id`:

1. **Which child to keep** — ops decision, typically:
   - Keep the child in `queued` / `running` / `starting` if it is the active retry attempt.
   - Otherwise keep the most recent non-terminal child, or the one whose worker actually progressed furthest.
   - Never keep two rows with the same parent; delete or re-parent orphans after review.

2. **Job histories** — terminal failed parents and their `retry_of_job_id` links are audit history. Do not delete parent jobs unless data-retention policy requires it. Remove or reassign **duplicate children** only.

3. **After cleanup** — re-run preflight until clean, then apply migration.

## Apply

Run `0073_inventory_jobs_retry_of_unique.sql` via your normal migration runner. The script is idempotent (`IF NOT EXISTS` on index).

## Rollback

```sql
DROP INDEX IF EXISTS UX_inventory_jobs_retry_of_job_id ON dbo.inventory_jobs;
```

Rollback removes the uniqueness guarantee only; it does not restore deleted duplicate rows.

## Reapply

1. Rollback (optional, if index exists in bad state).
2. Preflight — must pass.
3. Re-run `0073_inventory_jobs_retry_of_unique.sql`.
