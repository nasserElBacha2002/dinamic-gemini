/*
Phase G1 — allow inventory-level capture sessions (aisle_id nullable).

Keeps backward compatibility:
- existing aisle-scoped sessions remain valid
- one-open-per-aisle uniqueness continues for non-null aisle_id
*/

IF EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_sessions')
      AND name = 'aisle_id'
      AND is_nullable = 0
)
BEGIN
    ALTER TABLE dbo.capture_sessions ALTER COLUMN aisle_id VARCHAR(36) NULL;
END
GO

IF EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'UQ_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID('dbo.capture_sessions')
)
BEGIN
    DROP INDEX UQ_capture_sessions_one_open_per_aisle ON dbo.capture_sessions;
END
GO

-- Filtered indexes cannot use NOT IN / != ; use repeated <> (same as 0018 / schema.sql).
CREATE UNIQUE NONCLUSTERED INDEX UQ_capture_sessions_one_open_per_aisle
    ON dbo.capture_sessions (inventory_id, aisle_id)
    WHERE aisle_id IS NOT NULL
      AND closed_at IS NULL
      AND status <> 'cancelled'
      AND status <> 'failed'
      AND status <> 'confirmed';
GO
