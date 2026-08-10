/*
  Rollback 0091_client_position_label_hierarchy.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_client_position_labels_client_hierarchy'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    DROP INDEX IX_client_position_labels_client_hierarchy ON dbo.client_position_labels;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_marker'
)
    ALTER TABLE dbo.client_position_labels DROP CONSTRAINT CK_client_position_labels_marker;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_level'
)
    ALTER TABLE dbo.client_position_labels DROP CONSTRAINT CK_client_position_labels_level;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_side'
)
    ALTER TABLE dbo.client_position_labels DROP CONSTRAINT CK_client_position_labels_side;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'marker_total') IS NOT NULL
    ALTER TABLE dbo.client_position_labels DROP COLUMN marker_total;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'marker_index') IS NOT NULL
    ALTER TABLE dbo.client_position_labels DROP COLUMN marker_index;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'level') IS NOT NULL
    ALTER TABLE dbo.client_position_labels DROP COLUMN level;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'side') IS NOT NULL
    ALTER TABLE dbo.client_position_labels DROP COLUMN side;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'pallet') IS NOT NULL
    ALTER TABLE dbo.client_position_labels DROP COLUMN pallet;
GO
