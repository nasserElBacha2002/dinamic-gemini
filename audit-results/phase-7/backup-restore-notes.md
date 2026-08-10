# Phase 7 — Backup / restore notes

## Physical BACKUP limitation (this host)

Docker SQL Server (`sqlserver` on localhost:1433) rejects `BACKUP DATABASE ... TO DISK` with **Error 3041** / `BackupDiskFile::OpenMedia` OS error 2. `DBCC CLONEDATABASE` targets also cannot be backed up. Evidence: container error log lines `BACKUP failed to complete the command`.

## Executed drill (logical)

Script: `scripts/release/run_backup_restore_drill.sh`

1. Create ephemeral `dinamic_phase7_backup_src`
2. Logical copy of `schema_migrations`, `inventories`, `aisles`, `inventory_jobs` from `dinamic-gemini`
3. Seed synthetic SUCCEEDED job
4. Logical restore into `dinamic_phase7_restore_test`
5. Verify schema version **0073**, index `UX_inventory_jobs_retry_of_job_id`, job counts
6. Start API with `EMBEDDED_WORKER_ENABLED=false` → `/ready=200`
7. Record duration

Result: `BACKUP_RESTORE_DRILL_OK` (`mode=logical_select_into`).

## Staging / production

Use native `BACKUP`/`RESTORE` (or managed snapshots) on SQL instances where Error 3041 does not apply. Keep COPY_ONLY for non-disruptive drills. Never run against production from developer laptops.
