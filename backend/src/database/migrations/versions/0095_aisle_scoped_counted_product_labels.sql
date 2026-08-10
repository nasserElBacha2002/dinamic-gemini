/*
  Version 0095 — D1 label_id count-once uniqueness is aisle-scoped (pasillo), not inventory.

  Before: UNIQUE(inventory_id, label_id) blocked the same physical sticker across aisles
          in one inventory (and reprocess of another pasillo reused prior claims).
  After:  UNIQUE(aisle_id, label_id); inventory_id retained for audit/traceability.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
      AND name = N'aisle_id'
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        ADD aisle_id VARCHAR(36) NULL;
END
GO

-- Backfill from job target (CODE_SCAN / pipeline claims).
UPDATE icpl
SET aisle_id = j.target_id
FROM dbo.inventory_counted_product_labels AS icpl
INNER JOIN dbo.inventory_jobs AS j
    ON j.id = icpl.first_job_id
   AND j.target_type = N'aisle'
WHERE icpl.aisle_id IS NULL
  AND NULLIF(LTRIM(RTRIM(icpl.first_job_id)), N'') IS NOT NULL;
GO

-- Backfill remaining from first position.
UPDATE icpl
SET aisle_id = p.aisle_id
FROM dbo.inventory_counted_product_labels AS icpl
INNER JOIN dbo.positions AS p
    ON p.id = icpl.first_position_id
WHERE icpl.aisle_id IS NULL;
GO

-- Orphan claims that cannot be scoped must not block the new unique index.
DELETE FROM dbo.inventory_counted_product_labels
WHERE aisle_id IS NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    DROP INDEX UQ_icpl_inventory_label ON dbo.inventory_counted_product_labels;
END
GO

IF EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
      AND name = N'aisle_id'
      AND is_nullable = 1
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        ALTER COLUMN aisle_id VARCHAR(36) NOT NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_icpl_aisle'
      AND parent_object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        ADD CONSTRAINT FK_icpl_aisle
            FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_aisle_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_icpl_aisle_label
        ON dbo.inventory_counted_product_labels(aisle_id, label_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_icpl_inventory_label
        ON dbo.inventory_counted_product_labels(inventory_id, label_id);
END
GO
