# AUDIT_DATABASE_V3.1.2.md

## 1. Summary

This document reports the database schema audit for Dinamic Inventory v3.1.2. It inventories tables, classifies them as active/legacy/transitional, identifies version-based naming, and notes migration risks.

## 2. Scope

- **Included:** `src/database/schema.sql`, `src/database/repository.py`, `src/infrastructure/repositories/sql_*.py`, and any code that references table names or executes SQL.
- **Excluded:** No data migration or schema changes were applied.

## 3. Findings

### 3.1 Table inventory

All tables are defined in `src/database/schema.sql`.

| Table | Purpose | Used by | Classification |
|-------|---------|---------|----------------|
| **jobs** | Legacy job lifecycle (video/photos pipeline): status, progress, outputs, paths | `database/repository.py` (JobsRepository), `jobs/worker.py`, `api/routes/jobs.py` (when DB enabled) | **Legacy** (active for v1 job flow) |
| **pallet_results** | One row per pipeline entity (pallet) per legacy job; includes source_image_id, traceability_status | PalletResultsRepository, worker push, get_job_result fallback | **Legacy** (active for v1) |
| **job_events** | Audit events per legacy job | JobEventsRepository, worker | **Legacy** (active for v1) |
| **inventories** | v3 inventories | SqlInventoryRepository | **Active** |
| **aisles** | v3 aisles | SqlAisleRepository | **Active** |
| **v3_jobs** | v3 domain Job (process_aisle); target_type, target_id, status, result_json | SqlJobRepository, V3JobExecutor, worker (v3 path) | **Active** (version-based name) |
| **source_assets** | v3 aisle assets (photos/videos) | SqlSourceAssetRepository | **Active** |
| **positions** | v3 positions (results) | SqlPositionRepository | **Active** |
| **product_records** | v3 product records per position | SqlProductRecordRepository | **Active** |
| **evidences** | v3 evidences | SqlEvidenceRepository | **Active** |
| **review_actions** | v3 review actions per position | SqlReviewActionRepository | **Active** |

### 3.2 Version-based and technical names

- **v3_jobs:** Only table with an explicit version prefix. Used by the active v3 job flow. **Candidate for rename** to a domain name (e.g. `aisle_jobs` or `jobs` if legacy `jobs` is eventually removed; see risks).
- **jobs:** Name is domain-like but tied to the legacy pipeline; distinct from domain entity `Job` persisted in `v3_jobs`. Naming is consistent with "legacy job record" in code comments.

### 3.3 Data usage trace

- **Legacy path:** `jobs` ← referenced by `pallet_results.job_id`, `job_events.job_id`. Created/updated by `JobsRepository`; read by `get_job`, status/result/report in `jobs.py`. Worker writes status, outputs, and pallet_results/events on success.
- **v3 path:** `v3_jobs` is the only job table written by V3JobExecutor and read by JobRepository (get_by_id, get_latest_by_target). No FK from v3 tables to `jobs`.
- **v3 domain tables:** inventories → aisles → source_assets, positions → product_records, evidences, review_actions. All accessed via SQL repositories in `src/infrastructure/repositories/`.

### 3.4 Naming consistency

- **Tables:** Mostly domain names (inventories, aisles, positions, …). Inconsistency: `v3_jobs` vs `jobs`.
- **Constraints:** FK and unique constraints use descriptive names (e.g. FK_aisles_inventory, UQ_aisles_inventory_code). No audit of index naming beyond schema file.

### 3.5 Conceptual duplication

- **Two job concepts:** (1) Legacy `jobs` row (video_path, report paths, status) for the file-based pipeline. (2) Domain `Job` in `v3_jobs` (target_type, target_id, job_type, status, result_json) for process_aisle. They serve different flows; duplication is architectural, not schema redundancy.

## 4. Classification

| Table | Classification | Note |
|-------|----------------|------|
| jobs | **Legacy** | Active only for v1/Stage 8 flow |
| pallet_results | **Legacy** | Same |
| job_events | **Legacy** | Same |
| inventories, aisles, source_assets, positions, product_records, evidences, review_actions | **Active** | v3 domain |
| v3_jobs | **Active** (transitional name) | v3 domain; name has version prefix |

## 5. Risks

- **Renaming v3_jobs:** All references are in `src/infrastructure/repositories/sql_job_repository.py` and possibly config/migrations. Rename requires a migration script and repository update in lockstep; no FK from other v3 tables to v3_jobs (only application-level association by target_id).
- **Removing legacy tables:** Dropping `jobs`, `pallet_results`, or `job_events` would break the legacy worker and v1 job creation/result/report. Safe only after v1 job flow is retired and any data preserved or migrated.

## 6. Recommendations

- Rename `v3_jobs` to a domain name (e.g. `aisle_jobs` or `jobs` after legacy `jobs` removal) in a dedicated migration; update SqlJobRepository in the same change set.
- Document the two job systems (legacy vs v3) and the conditions under which each table is written/read.
- Before any table drop, confirm no script or external system reads legacy tables.

## 7. Candidate next-stage actions

- **Stage 3 (DB normalization):** Add migration to rename `v3_jobs` to target name; update `sql_job_repository.py` and run tests. Optionally add a view or synonym for temporary backward compatibility if needed.
- **Stage 2/3 coordination:** If Stage 2 removes the legacy job creation/status/result API and worker path, plan migration to drop or archive `jobs`, `pallet_results`, `job_events` in a later version; do not drop in v3.1.2 without explicit product decision.
