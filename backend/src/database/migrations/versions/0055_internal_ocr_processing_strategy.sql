-- Phase 4 — INTERNAL_OCR execution strategy.
-- Additive + idempotent. Widens inventory_jobs.execution_strategy CHECK to allow
-- 'INTERNAL_OCR'. OCR evidence lives in the common ImageProcessingResult.evidence
-- contract (and job.engine_params_json snapshot); no dedicated dead table.
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
