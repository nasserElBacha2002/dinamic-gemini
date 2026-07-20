-- Phase 3 — CODE_SCAN execution strategy.
-- Additive + idempotent. Widens the inventory_jobs.execution_strategy CHECK to allow
-- 'CODE_SCAN' and adds an optional per-attempt code-scan detections table for audit.
-- Keep aligned with backend/src/database/schema.sql.

-- 1) Guard: reject unknown persisted execution_strategy values before touching the constraint.
IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE execution_strategy NOT IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN')
)
BEGIN
    THROW 50056, 'Invalid inventory_jobs.execution_strategy values found; fix data before 0053 constraint widening.', 1;
END;
GO

-- 2) Recreate the execution_strategy CHECK to include CODE_SCAN (drop-then-add; idempotent).
IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs DROP CONSTRAINT CK_inventory_jobs_execution_strategy;
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_execution_strategy
    CHECK (execution_strategy IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN'));
GO

-- 3) Optional per-attempt code-scan detections audit table (distinct from the sync-API
--    aisle_code_scan_detections table, which is left untouched).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_asset_code_scan_detections')
BEGIN
    CREATE TABLE job_asset_code_scan_detections (
        id VARCHAR(64) NOT NULL PRIMARY KEY,
        job_id VARCHAR(64) NOT NULL,
        asset_id VARCHAR(64) NOT NULL,
        attempt_id VARCHAR(64) NULL,
        detection_index INT NOT NULL,
        symbology VARCHAR(32) NOT NULL,
        normalized_value NVARCHAR(512) NULL,
        raw_value_hash VARCHAR(64) NULL,
        bounding_box_json NVARCHAR(MAX) NULL,
        scanner_name VARCHAR(64) NULL,
        scanner_version VARCHAR(64) NULL,
        preprocessing_variant VARCHAR(32) NULL,
        is_selected BIT NOT NULL DEFAULT (0),
        created_at DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_job_asset_code_scan_detections_attempt_idx
            UNIQUE (attempt_id, detection_index)
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'IX_job_asset_code_scan_detections_job_asset'
)
    CREATE INDEX IX_job_asset_code_scan_detections_job_asset
    ON job_asset_code_scan_detections (job_id, asset_id);
GO
