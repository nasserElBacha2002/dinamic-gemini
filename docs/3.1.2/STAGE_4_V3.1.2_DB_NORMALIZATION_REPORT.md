# STAGE_4_V3.1.2_DB_NORMALIZATION_REPORT.md

## 1. Summary

Stage 4 normalizes the database schema so that the active job table uses a **domain-oriented name** instead of the version-based `v3_jobs`. The table was renamed to **`inventory_jobs`**, and all repository and schema references were updated. Legacy tables (`jobs`, `pallet_results`, `job_events`) were **kept** and documented; they are still used by the worker fallback path and by tests. No legacy table was removed.

---

## 2. Active table classification

Re-audit was performed against the **post–Stage 3** codebase (v1 routes removed, v3-only API).

| Table | Current usage | Used by | Classification | Action |
|-------|----------------|--------|----------------|--------|
| **v3_jobs** | Domain Job (process_aisle): save, get_by_id, get_latest_by_target | SqlJobRepository, V3JobExecutor, start_aisle_processing use case, list_aisles_with_status, get_aisle_processing_status | **Active** (version-based name) | **Renamed** to `inventory_jobs` |
| **inventory_jobs** | Same as above after rename | SqlJobRepository (all queries) | **Active** | Target name for normalized schema |
| **jobs** | Legacy job lifecycle: create, get, update status/progress/outputs/error | job_store (create_job, get_job, update_job when DB enabled), worker (get_job, update_job, _push_success_to_db) | **Legacy, operationally required** (worker fallback + test-used) | **Keep** |
| **pallet_results** | One row per pipeline entity per legacy job | PalletResultsRepository, worker _push_success_to_db, job_store get_pallet_results | **Legacy, operationally required** (worker fallback) | **Keep** |
| **job_events** | Audit events per legacy job | JobEventsRepository, worker (_push_success_to_db, insert_event on error) | **Legacy, operationally required** (worker fallback) | **Keep** |
| **inventories, aisles, source_assets, positions, product_records, evidences, review_actions** | v3 domain CRUD | Sql*Repository in infrastructure | **Active** | No change (already domain-named) |

**Evidence (code paths):**

- **v3_jobs → inventory_jobs:** Only referenced in `src/infrastructure/repositories/sql_job_repository.py` (queries and log messages). No FK from other v3 tables to this table.
- **jobs:** `src/database/repository.py` (JobsRepository), `src/jobs/job_store.py` (_db_repos → create_job, get_job, update_job), `src/jobs/worker.py` (get_job, update_job, _push_success_to_db).
- **pallet_results:** `src/database/repository.py` (PalletResultsRepository), worker _push_success_to_db, job_store get_pallet_results.
- **job_events:** `src/database/repository.py` (JobEventsRepository), worker _push_success_to_db and insert_event on error.

---

## 3. Rename decisions

| Current table | Proposed table | Reason |
|---------------|----------------|--------|
| v3_jobs | **inventory_jobs** | Domain name for “jobs in the inventory workflow” (process_aisle); aligns with inventories, aisles; removes version prefix. |

No other active table had version-based naming.

---

## 4. Migration details

**Location:** `src/database/schema.sql` (in place; no separate migrations folder).

### Supported DB states (script is idempotent)

| State | Condition | Script behavior |
|-------|-----------|-----------------|
| **Fresh install** | Neither `v3_jobs` nor `inventory_jobs` exists | Creates `inventory_jobs` and index `IX_inventory_jobs_target`. |
| **Pre-migration** | `v3_jobs` exists, `inventory_jobs` does not | Renames table to `inventory_jobs`, then renames index to `IX_inventory_jobs_target` (only if index still has old name; see below). Data preserved. |
| **Already migrated** | `inventory_jobs` exists | Outer `IF NOT EXISTS (inventory_jobs)` is false; entire block skipped. No action. |

### Unsupported / operator intervention

- **Both `v3_jobs` and `inventory_jobs` exist** (e.g. manual partial run or copy): The script does not modify either table (it only runs when `inventory_jobs` is missing). The application uses `inventory_jobs`. Operator may drop or archive `v3_jobs` if desired; no automatic resolution.

### Index rename hardening (corrective pass)

The index rename is guarded with `sys.indexes`: `EXEC sp_rename` for the index runs only if an index named `IX_v3_jobs_target` exists on `inventory_jobs`. This avoids failure if the index was already renamed (e.g. re-run after partial manual rename) and keeps the migration idempotent for the supported pre-migration state.

### Rollback

To revert, run `EXEC sp_rename 'dbo.inventory_jobs', 'v3_jobs'` and rename the index back to `IX_v3_jobs_target`, then redeploy code that references `v3_jobs`. Not recommended after deployment; document if required.

---

## 5. Code adaptations

| File | Change |
|------|--------|
| `src/database/schema.sql` | Create or migrate to `inventory_jobs`: new installs create the table; existing DBs with `v3_jobs` get a rename + guarded index rename (see §4). Supported/unsupported states documented in block comment. |
| `src/infrastructure/repositories/sql_job_repository.py` | All SQL: `v3_jobs` → `inventory_jobs`. Log messages: "v3_jobs row" → "inventory_jobs row". Docstring updated to mention inventory_jobs. |

**No changes to:**

- Worker, job_store, database/repository.py (they do not reference the v3 job table name; they use JobsRepository/PalletResultsRepository/JobEventsRepository for legacy tables).
- Use cases (they depend on JobRepository port, not table name).
- Tests (no tests reference `v3_jobs` in SQL; they use repositories or in-memory implementations).

---

## 6. Legacy tables kept or removed

Classification is **legacy, operationally required**: still used by the worker fallback path (and by tests for `jobs`). Not “test-only”; removal would break the fallback or tests.

| Table | Classification | Decision | Rationale |
|-------|----------------|----------|-----------|
| jobs | Legacy, operationally required (worker fallback + test-used) | **Keep** | Worker fallback: run_job loads via get_job, updates status/outputs; _push_success_to_db writes to jobs. job_store.create_job used by tests (e.g. test_stage8_db, test_e2e_v2_2). |
| pallet_results | Legacy, operationally required (worker fallback) | **Keep** | Worker _push_success_to_db inserts rows; FK to jobs(id). Required for legacy job success path. |
| job_events | Legacy, operationally required (worker fallback) | **Keep** | Worker inserts events on success and on error. Required for legacy audit path. |

**Removed:** None. No table was dropped. Removal would require retiring the legacy job flow and test coverage that depends on it.

---

## 7. Risks and deferred items

- **Legacy tables:** Still in use by worker fallback and tests. Future stage may retire the legacy job flow and then consider archiving or dropping `jobs`, `pallet_results`, `job_events` after product approval and data handling.
- **Schema application order:** If schema.sql is run against a DB that already has `inventory_jobs` (e.g. after a prior run), the block is idempotent. If a DB has both `v3_jobs` and `inventory_jobs` (e.g. manual partial run), the script does not rename again; operator must resolve.
- **SQL Server only:** Migration uses `sp_rename` and `sys.tables`; not validated for other backends. In-memory repos are unchanged and do not use schema.

---

## 8. Validation notes

- **Code:** All references to `v3_jobs` in `src/` were updated to `inventory_jobs` in `sql_job_repository.py` and `schema.sql`. Grep for `v3_jobs` in `src/` shows no remaining executable references (schema.sql keeps `v3_jobs` only in migration condition and comments).
- **App boot:** Backend starts; JobRepository is resolved from v3_deps (SqlJobRepository when SQL Server enabled). No table name is passed at runtime; repository uses the new name in SQL.
- **Tests:** No test file references the `v3_jobs` table name; tests use in-memory repos or the application port. Existing tests that use SqlJobRepository will run against a DB that has been migrated to `inventory_jobs`.
- **Schema script — three supported scenarios (by code inspection):**
  1. **Fresh install:** `IF NOT EXISTS (inventory_jobs)` true → enter block; `IF EXISTS (v3_jobs)` false → ELSE: create table and index. Correct.
  2. **Pre-migration:** `IF NOT EXISTS (inventory_jobs)` true → enter block; `IF EXISTS (v3_jobs)` true → rename table, then rename index only if `IX_v3_jobs_target` exists. Correct.
  3. **Already migrated:** `IF NOT EXISTS (inventory_jobs)` false → block skipped. Correct.

---

**Document version:** 1.1 (corrective pass: supported/unsupported states, index guard, legacy classification, validation scenarios)  
**Stage:** 4 — Database normalization  
**Date:** 2025-03-06
