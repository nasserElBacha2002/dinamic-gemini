-- =============================================================================
-- Phase 14 — DRAFT: Legacy Stage-8 SQL tables DROP (NOT in versions/ yet)
-- =============================================================================
--
-- This file lives under migrations/drafts/ so it does NOT affect
-- get_required_schema_version() or auto-migration ordering.
--
-- When Phase 14.6 is approved: copy (or move) to:
--   backend/src/database/migrations/versions/0015_drop_legacy_jobs.sql
-- after renumbering if another 0015 already shipped.
--
-- Target tables (legacy pipeline — NOT v3):
--   dbo.job_events      (FK -> jobs)
--   dbo.pallet_results  (FK -> jobs)
--   dbo.jobs
--
-- PREREQUISITES — ALL mandatory before execution
-- ---------------------------------------------------------------------------
-- 1. Product: legacy pipeline retired (Phase 13 STATE C + sign-off).
-- 2. Code: legacy SQL path disabled; zero legacy writes in prod (verified).
-- 3. Staging: dry-run complete; app/workers/APIs/analytics OK post-DROP.
-- 4. DB: archive snapshot / BACPAC of the three tables.
-- 5. FK audit: no other tables reference jobs / pallet_results / job_events.
--
-- REVERSIBILITY: IRREVERSIBLE by SQL alone. Rollback = restore from backup.
-- =============================================================================

IF OBJECT_ID(N'dbo.job_events', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.job_events;
END
GO

IF OBJECT_ID(N'dbo.pallet_results', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.pallet_results;
END
GO

IF OBJECT_ID(N'dbo.jobs', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.jobs;
END
GO
