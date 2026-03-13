# Stage 4 v3.1.2 — Corrective Pass Report (DB Normalization)

## 1. Summary

A **corrective pass / hardening review** was performed on the existing Stage 4 DB normalization implementation. The goal was to make the normalization more robust, safer to run, and better documented without changing the architectural direction: `inventory_jobs` remains the normalized active table; legacy tables remain.

**Reviewed:** `src/database/schema.sql`, `src/infrastructure/repositories/sql_job_repository.py`, `STAGE_4_V3.1.2_DB_NORMALIZATION_REPORT.md`, and the wider repo for `v3_jobs` references.

**Outcome:** Index rename was hardened with an explicit `sys.indexes` guard; supported vs unsupported DB states were documented in schema and report; stale `v3_jobs` references in active guidance (skill/reference) were updated; legacy table classification was refined; validation of the three supported scenarios was documented. No destructive or scope-broadening changes.

---

## 2. Concern-by-concern assessment

### Concern 1 — Robustness of index rename in schema.sql

**Assessment:** The original migration ran `sp_rename` for the index unconditionally after renaming the table. If the index had already been renamed (e.g. manual re-run or partial migration), the second `sp_rename` would fail.

**Evidence:** In `schema.sql`, the block was:
```sql
EXEC sp_rename 'dbo.v3_jobs', 'inventory_jobs';
EXEC sp_rename 'dbo.inventory_jobs.IX_v3_jobs_target', 'IX_inventory_jobs_target', 'INDEX';
```
No check for index existence. SQL Server `sp_rename` for INDEX requires the current index name; if it was already `IX_inventory_jobs_target`, or missing, the call could error.

**Action taken:** A guard was added using `sys.indexes`: the index rename runs only if an index named `IX_v3_jobs_target` exists on `dbo.inventory_jobs`:
```sql
IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.inventory_jobs') AND name = 'IX_v3_jobs_target')
    EXEC sp_rename 'dbo.inventory_jobs.IX_v3_jobs_target', 'IX_inventory_jobs_target', 'INDEX';
```
This makes the migration idempotent for the pre-migration state and safe if the index was already renamed. The path is correct (`dbo.inventory_jobs.IX_v3_jobs_target` after the table rename). Fresh installs are unchanged (they create the table with `IX_inventory_jobs_target` and never run the index rename).

---

### Concern 2 — Clarify supported vs unsupported DB states

**Assessment:** The report described behavior for fresh DB, DB with `v3_jobs`, and already-migrated DB, but did not explicitly call out unsupported or manual mixed states.

**Evidence:** Report section 7 mentioned “If a DB has both v3_jobs and inventory_jobs … the script does not rename again; operator must resolve” but there was no single place listing supported vs unsupported states.

**Action taken:**
- **In schema.sql:** A block comment was added above the `inventory_jobs` block listing:
  - **Supported:** (1) Fresh install, (2) Pre-migration (v3_jobs exists, inventory_jobs does not), (3) Already migrated (inventory_jobs exists).
  - **Unsupported:** Both `v3_jobs` and `inventory_jobs` exist; script does not touch tables; operator may drop/archive `v3_jobs` if desired.
- **In report:** Section 4 was restructured with “Supported DB states” and “Unsupported / operator intervention” subsections and a table for the three supported states. No logic was added to auto-resolve broken manual states.

---

### Concern 3 — Stale v3_jobs references outside src/

**Assessment:** Several references to `v3_jobs` remained in docs and in Cursor skill/reference files. Tests had no references.

**Evidence (grep across repo):**

| Location | Classification | Action |
|----------|----------------|--------|
| `docs/3.1.2/AUDIT_JOB_LIFECYCLE_V3.1.2.md` | Historical audit; describes persistence and recommendations | Left as-is (historical; not operator runbook). |
| `docs/3.1.2/AUDIT_DATABASE_V3.1.2.md` | Historical audit; pre–Stage 4 state | Left as-is. |
| `docs/3.1.2/STAGE_1_FINDINGS_SUMMARY_V3.1.2.md` | Historical findings | Left as-is. |
| `docs/3.1.2/STAGE_2_V3.1.2_BACKEND_LEGACY_CLEANUP_REPORT.md` | Historical report | Left as-is. |
| `docs/3.1.2/AUDIT_BACKEND_V3.1.2.md` | Historical audit | Left as-is. |
| `docs/3.1.2/STAGE_4_V3.1.2_DB_NORMALIZATION_REPORT.md` | Current report; mentions v3_jobs as “renamed from” | Kept for context; report updated with supported states and hardening. |
| `.cursor/skills/cv-inventory-repo-assistant/SKILL.md` | **Active guidance** (Persistence, Jobs bullets) | **Updated:** “v3_jobs” → “inventory_jobs”. |
| `.cursor/skills/cv-inventory-repo-assistant/reference.md` | **Active reference** (database row) | **Updated:** “v3_jobs” → “inventory_jobs”. |
| `.cursor/CURSOR_SKILLS_UPDATE_PLAN.md` | Planning doc | Left as-is (low impact). |
| `src/database/schema.sql` | Migration condition and comments | Kept: condition `IF EXISTS (v3_jobs)` and comments are correct. |
| `src/infrastructure/repositories/sql_job_repository.py` | Docstring “normalized from v3_jobs in Stage 4” | Kept as intentional historical note. |
| **tests/** | No matches | No changes. |

**Action taken:** Only **stale executable/guidance** references were updated: `SKILL.md` and `reference.md`. Historical audit and stage docs were not rewritten to avoid scope creep and because they are not used as operator runbooks.

---

### Concern 4 — Improve classification of legacy tables

**Assessment:** The report used “Legacy but still required” for `jobs`, `pallet_results`, and `job_events`. A more precise classification improves clarity.

**Evidence:** All three tables are used by the worker fallback path. `jobs` is also used by tests (job_store create_job, get_job, update_job). None are “test-only”; removal would break the fallback or tests.

**Action taken:** Classification was refined to **“Legacy, operationally required”** with a short qualifier:
- **jobs:** Legacy, operationally required (worker fallback + test-used).
- **pallet_results:** Legacy, operationally required (worker fallback).
- **job_events:** Legacy, operationally required (worker fallback).

No change to keep/remove decisions. Section 6 of the Stage 4 report was updated with a classification column and this wording.

---

### Concern 5 — Consistency of naming and messaging after normalization

**Assessment:** Active code and migration comments were checked for stale “v3_jobs” wording.

**Evidence:**
- `sql_job_repository.py`: All SQL and log messages use `inventory_jobs`. Docstring says “Persists … to the inventory_jobs table (normalized from v3_jobs in Stage 4)” — kept as historical context.
- `schema.sql`: Comment “Normalized from v3_jobs (Stage 4)” kept; new comments use “inventory_jobs” and “v3_jobs” only where describing the migration (supported/unsupported states, index guard).

**Action taken:** No further edits. Active code and logs are consistent with `inventory_jobs`; the only remaining “v3_jobs” in `src/` is in schema migration logic and docstring history, which is correct.

---

### Concern 6 — Validation quality of the migration logic

**Assessment:** The three supported scenarios needed explicit validation.

**Evidence (code inspection of schema block):**

1. **Fresh install (neither v3_jobs nor inventory_jobs):**  
   `IF NOT EXISTS (inventory_jobs)` → true → enter block. `IF EXISTS (v3_jobs)` → false → ELSE branch: create `inventory_jobs` and `IX_inventory_jobs_target`. Correct.

2. **Pre-migration (v3_jobs exists, inventory_jobs does not):**  
   `IF NOT EXISTS (inventory_jobs)` → true → enter block. `IF EXISTS (v3_jobs)` → true → rename table, then conditionally rename index if `IX_v3_jobs_target` exists. Correct.

3. **Already migrated (inventory_jobs exists):**  
   `IF NOT EXISTS (inventory_jobs)` → false → entire block skipped. Correct.

**Action taken:** Validation reasoning was added to the Stage 4 report (Section 8) for all three scenarios. No automated DB test was run; validation is by code inspection. The report states this.

---

## 3. Code and migration changes applied

| File | Change |
|------|--------|
| `src/database/schema.sql` | (1) Block comment added: supported states (fresh, pre-migration, already migrated) and unsupported state (both tables exist). (2) Index rename wrapped in `IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.inventory_jobs') AND name = 'IX_v3_jobs_target')`. |
| `.cursor/skills/cv-inventory-repo-assistant/SKILL.md` | Persistence and Jobs bullets: “v3_jobs” → “inventory_jobs”. |
| `.cursor/skills/cv-inventory-repo-assistant/reference.md` | Database row: “v3_jobs” → “inventory_jobs”. |
| `docs/3.1.2/STAGE_4_V3.1.2_DB_NORMALIZATION_REPORT.md` | Section 4: Replaced with “Supported DB states” table, “Unsupported / operator intervention”, and “Index rename hardening” subsection. Section 2: Legacy rows use classification “Legacy, operationally required (…)”. Section 6: Classification column and refined wording. Section 8: Validation notes for the three scenarios. Document version set to 1.1. |

---

## 4. Supported migration states

**Supported (script is idempotent):**

| State | Condition | Result |
|-------|-----------|--------|
| Fresh install | No `v3_jobs`, no `inventory_jobs` | Creates `inventory_jobs` and `IX_inventory_jobs_target`. |
| Pre-migration | `v3_jobs` exists, no `inventory_jobs` | Renames table to `inventory_jobs`; renames index to `IX_inventory_jobs_target` only if it still exists as `IX_v3_jobs_target`. |
| Already migrated | `inventory_jobs` exists | No action (block skipped). |

**Unsupported (operator intervention):**

- **Both `v3_jobs` and `inventory_jobs` exist:** Script does not modify tables. Application uses `inventory_jobs`. Operator may drop or archive `v3_jobs` manually.

---

## 5. Remaining deferred items

- **Historical docs:** AUDIT_*.md, STAGE_1, STAGE_2, etc. still mention `v3_jobs` in a pre–Stage 4 sense. Intentionally not updated; they are historical, not operator runbooks.
- **Real DB test:** Validation was by code inspection only. Running schema.sql against real SQL Server instances (fresh, pre-migration, post-migration) would strengthen validation; deferred to environment availability.
- **Legacy table removal:** Still deferred; no change to keep/remove decisions. Future stage may retire legacy job flow and then consider archiving/dropping `jobs`, `pallet_results`, `job_events`.

---

## 6. Validation notes

- **Index rename path:** Confirmed: after table rename, the table is `dbo.inventory_jobs` and the index is still named `IX_v3_jobs_target` until we rename it. `sp_rename 'dbo.inventory_jobs.IX_v3_jobs_target', 'IX_inventory_jobs_target', 'INDEX'` is correct. Guard uses `OBJECT_ID('dbo.inventory_jobs')` and `name = 'IX_v3_jobs_target'`.
- **Three scenarios:** Documented in Section 8 of the Stage 4 report and in Section 2 (Concern 6) of this report. No automated test was run; validation is by code reasoning.
- **Normalization preserved:** All application code and active guidance use `inventory_jobs`. No rollback of the Stage 4 rename.

---

**Document:** Stage 4 corrective pass report  
**Date:** 2025-03-06
