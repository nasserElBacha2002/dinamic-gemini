# Phase 7 — Migration validation report

## Chain

- Historical migrations **0001–0072**: KEEP (never edit applied history).
- **0073** `UX_inventory_jobs_retry_of_job_id`: additive filtered unique index + duplicate preflight.

## 0073 checklist

| Scenario | Status | Evidence |
| -------- | ------ | -------- |
| Preflight lists duplicates | PASS (tool) | `scripts/ops/preflight_0073_retry_of_duplicates.py` + unit tests |
| Auto-resolve duplicates | N/A by design | Manual resolution per `0073_README.md` |
| Apply idempotent | documented | SQL `IF NOT EXISTS` index create |
| Rollback | documented | `DROP INDEX UX_inventory_jobs_retry_of_job_id` |
| Reapply | documented | re-run migration after rollback |
| Helper script | added | `scripts/release/validate_migration_0073.sh` |

## Empty DB → latest

Run in ops/staging (not auto-run here against prod):

```bash
# create empty DB, point SQLSERVER_* at it
cd backend && python scripts/db_migrate.py -- apply
python scripts/db_migrate.py -- status
bash ../scripts/release/validate_migration_0073.sh
```

## Limitations

Full empty-DB apply/rollback on a throwaway SQL instance should be executed in CI/staging before production cutover. Local helper documents steps; this report does not claim a production DB was wiped.
