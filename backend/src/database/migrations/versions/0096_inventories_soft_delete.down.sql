/*
  Rollback 0096 — drop soft-delete columns from inventories.
  Safe only when no application code depends on deleted_at/deleted_by.
*/

IF EXISTS (
    SELECT * FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.inventories')
      AND name = N'IX_inventories_deleted_at'
)
BEGIN
    DROP INDEX IX_inventories_deleted_at ON dbo.inventories;
END
GO

IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventories') AND name = N'deleted_by'
)
BEGIN
    ALTER TABLE dbo.inventories DROP COLUMN deleted_by;
END
GO

IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventories') AND name = N'deleted_at'
)
BEGIN
    ALTER TABLE dbo.inventories DROP COLUMN deleted_at;
END
GO
