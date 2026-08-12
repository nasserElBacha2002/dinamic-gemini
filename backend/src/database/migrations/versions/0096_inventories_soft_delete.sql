/*
  Version 0096 — Soft delete for inventories (additive).

  deleted_at NULL  = active inventory (default for all existing rows)
  deleted_at set   = soft-deleted; excluded from normal list/get API paths
  deleted_by       = optional actor id (AuthUser.id) when known

  No physical DELETE; dependent aisles/jobs/assets/positions remain intact.
*/

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventories') AND name = N'deleted_at'
)
BEGIN
    ALTER TABLE dbo.inventories ADD deleted_at DATETIME2 NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventories') AND name = N'deleted_by'
)
BEGIN
    ALTER TABLE dbo.inventories ADD deleted_by VARCHAR(64) NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.inventories')
      AND name = N'IX_inventories_deleted_at'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_inventories_deleted_at
        ON dbo.inventories (deleted_at)
        WHERE deleted_at IS NULL;
END
GO
