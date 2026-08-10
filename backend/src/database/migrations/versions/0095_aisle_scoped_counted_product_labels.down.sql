/*
  Rollback 0095 — restore inventory-scoped UNIQUE(inventory_id, label_id).

  Note: aisle_id column is dropped; historical aisle scope is lost on rollback.
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_aisle_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    DROP INDEX UQ_icpl_aisle_label ON dbo.inventory_counted_product_labels;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    DROP INDEX IX_icpl_inventory_label ON dbo.inventory_counted_product_labels;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_icpl_aisle'
      AND parent_object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        DROP CONSTRAINT FK_icpl_aisle;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
      AND name = N'aisle_id'
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        DROP COLUMN aisle_id;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_icpl_inventory_label
        ON dbo.inventory_counted_product_labels(inventory_id, label_id);
END
GO
