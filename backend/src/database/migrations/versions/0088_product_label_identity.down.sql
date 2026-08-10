/*
  0088_product_label_identity.down.sql
  Rollback for 0088_product_label_identity.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_product_records_label_id'
      AND object_id = OBJECT_ID(N'dbo.product_records')
)
    DROP INDEX IX_product_records_label_id ON dbo.product_records;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.product_records') AND name = N'label_id'
)
    ALTER TABLE dbo.product_records DROP COLUMN label_id;
GO

IF OBJECT_ID(N'dbo.inventory_counted_product_labels', N'U') IS NOT NULL
    DROP TABLE dbo.inventory_counted_product_labels;
GO

IF OBJECT_ID(N'dbo.issued_product_labels', N'U') IS NOT NULL
    DROP TABLE dbo.issued_product_labels;
GO
