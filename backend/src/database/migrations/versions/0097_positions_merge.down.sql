/*
  Rollback 0097 — drop position merge columns (additive reverse).
*/

IF EXISTS (
    SELECT * FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.positions')
      AND name = N'IX_positions_merged_into'
)
BEGIN
    DROP INDEX IX_positions_merged_into ON dbo.positions;
END
GO

IF EXISTS (
    SELECT * FROM sys.check_constraints
    WHERE name = N'CK_positions_merged_into_not_self'
      AND parent_object_id = OBJECT_ID(N'dbo.positions')
)
BEGIN
    ALTER TABLE dbo.positions DROP CONSTRAINT CK_positions_merged_into_not_self;
END
GO

IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_at'
)
BEGIN
    ALTER TABLE dbo.positions DROP COLUMN merged_at;
END
GO

IF EXISTS (
    SELECT * FROM sys.foreign_keys
    WHERE name = N'FK_positions_merged_into' AND parent_object_id = OBJECT_ID(N'dbo.positions')
)
BEGIN
    ALTER TABLE dbo.positions DROP CONSTRAINT FK_positions_merged_into;
END
GO

IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_into_position_id'
)
BEGIN
    ALTER TABLE dbo.positions DROP COLUMN merged_into_position_id;
END
GO
