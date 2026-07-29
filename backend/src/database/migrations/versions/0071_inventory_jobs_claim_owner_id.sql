-- Phase 1 corrections: worker claim ownership distinct from execution_id.
-- Additive / idempotent. Keep aligned with backend/src/database/schema.sql.
-- Formal rollback (dev/test only):
--   ALTER TABLE inventory_jobs DROP COLUMN claim_owner_id;

IF COL_LENGTH('inventory_jobs', 'claim_owner_id') IS NULL
BEGIN
    ALTER TABLE inventory_jobs ADD claim_owner_id VARCHAR(64) NULL;
END
GO
