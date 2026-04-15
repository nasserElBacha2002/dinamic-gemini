-- Run-scoped review audit: nullable job_id on review_actions (legacy rows stay NULL).
-- Backfill from positions.job_id where the position is run-scoped.
--
-- Maintenance: keep aligned with backend/src/database/schema.sql (review_actions job_id block).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('review_actions') AND name = 'job_id')
    ALTER TABLE review_actions ADD job_id VARCHAR(36) NULL;
GO

UPDATE ra
SET ra.job_id = p.job_id
FROM review_actions ra
INNER JOIN positions p ON p.id = ra.position_id
WHERE ra.job_id IS NULL AND p.job_id IS NOT NULL;
GO
