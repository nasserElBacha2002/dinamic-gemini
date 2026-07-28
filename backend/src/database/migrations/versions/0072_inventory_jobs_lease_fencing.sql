-- Phase 3: job lease fencing (monotonic token + expiry).
-- Additive / idempotent. Keep aligned with backend/src/database/schema.sql.
-- Reuses claim_owner_id as the lease owner (no duplicate lease_owner_id column).
-- Formal rollback (dev/test only):
--   ALTER TABLE inventory_jobs DROP COLUMN lease_fencing_token;
--   ALTER TABLE inventory_jobs DROP COLUMN lease_expires_at;
--   ALTER TABLE inventory_jobs DROP COLUMN lease_acquired_at;
-- Do not drop columns with production data without an explicit ops plan.

IF COL_LENGTH('inventory_jobs', 'lease_fencing_token') IS NULL
BEGIN
    ALTER TABLE inventory_jobs ADD lease_fencing_token BIGINT NOT NULL
        CONSTRAINT DF_inventory_jobs_lease_fencing_token DEFAULT (0);
END
GO

IF COL_LENGTH('inventory_jobs', 'lease_expires_at') IS NULL
BEGIN
    ALTER TABLE inventory_jobs ADD lease_expires_at DATETIME2 NULL;
END
GO

IF COL_LENGTH('inventory_jobs', 'lease_acquired_at') IS NULL
BEGIN
    ALTER TABLE inventory_jobs ADD lease_acquired_at DATETIME2 NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'IX_inventory_jobs_lease_expiry'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_inventory_jobs_lease_expiry
        ON inventory_jobs(status, lease_expires_at)
        WHERE lease_expires_at IS NOT NULL;
END
GO
