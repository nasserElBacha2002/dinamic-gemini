-- Phase 4 — INTERNAL_OCR execution strategy.
-- Additive + idempotent. Widens inventory_jobs.execution_strategy CHECK to allow
-- 'INTERNAL_OCR' and adds an optional per-attempt OCR evidence audit table.
-- Keep aligned with backend/src/database/schema.sql.

-- 1) Guard: reject unknown persisted execution_strategy values before touching the constraint.
IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE execution_strategy NOT IN (
        'LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN', 'INTERNAL_OCR'
    )
)
BEGIN
    THROW 50058, 'Invalid inventory_jobs.execution_strategy values found; fix data before 0055 constraint widening.', 1;
END;
GO

-- 2) Recreate the execution_strategy CHECK to include INTERNAL_OCR (drop-then-add; idempotent).
IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs DROP CONSTRAINT CK_inventory_jobs_execution_strategy;
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_execution_strategy
    CHECK (execution_strategy IN (
        'LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN', 'INTERNAL_OCR'
    ));
GO

-- 3) Optional per-attempt OCR evidence audit table (text hash + variant metadata only).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_asset_internal_ocr_evidence')
BEGIN
    CREATE TABLE job_asset_internal_ocr_evidence (
        id VARCHAR(64) NOT NULL PRIMARY KEY,
        job_id VARCHAR(64) NOT NULL,
        asset_id VARCHAR(64) NOT NULL,
        attempt_id VARCHAR(64) NULL,
        engine_name VARCHAR(64) NULL,
        engine_version VARCHAR(64) NULL,
        preprocessing_variant VARCHAR(64) NULL,
        variants_attempted INT NULL,
        confidence FLOAT NULL,
        full_text_sha256 VARCHAR(64) NULL,
        duration_ms INT NULL,
        status VARCHAR(32) NULL,
        created_at DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME())
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'IX_job_asset_internal_ocr_evidence_job_asset'
)
    CREATE INDEX IX_job_asset_internal_ocr_evidence_job_asset
    ON job_asset_internal_ocr_evidence (job_id, asset_id);
GO
