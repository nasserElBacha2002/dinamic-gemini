-- Phase 3 corrections — harden job_asset_processing_states for SINGLE_ASSET code scan.
-- Additive + idempotent. Ensures the SINGLE_ASSET execution_scope and the active_result_id
-- column are supported, and constrains execution_scope to the known values. Nothing breaking:
-- both columns already exist from 0051; this only adds a guarded CHECK constraint.
-- Keep aligned with backend/src/database/schema.sql.

-- 1) Defensive: ensure active_result_id exists (it was introduced in 0051; guard for old DBs).
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('job_asset_processing_states') AND name = 'active_result_id'
)
    ALTER TABLE job_asset_processing_states ADD active_result_id VARCHAR(36) NULL;
GO

-- 2) Defensive: ensure execution_scope exists (introduced in 0051; guard for old DBs).
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('job_asset_processing_states') AND name = 'execution_scope'
)
    ALTER TABLE job_asset_processing_states ADD execution_scope VARCHAR(32) NULL;
GO

-- 3) Guard: reject unknown persisted execution_scope values before adding the constraint.
IF EXISTS (
    SELECT 1 FROM job_asset_processing_states
    WHERE execution_scope IS NOT NULL
      AND execution_scope NOT IN ('AISLE_BATCH', 'SINGLE_ASSET')
)
BEGIN
    THROW 50057, 'Invalid job_asset_processing_states.execution_scope values found; fix data before 0054 constraint.', 1;
END;
GO

-- 4) Add the CHECK (NULL allowed; only AISLE_BATCH | SINGLE_ASSET otherwise). Idempotent.
IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_job_asset_processing_states_execution_scope'
)
    ALTER TABLE job_asset_processing_states ADD CONSTRAINT CK_job_asset_processing_states_execution_scope
    CHECK (execution_scope IS NULL OR execution_scope IN ('AISLE_BATCH', 'SINGLE_ASSET'));
GO

-- Note: the unique manual coverage index (one manual/code-scan position per (job_id,
-- source_asset_id)) already exists on manual_image_coverage; not re-created here.
