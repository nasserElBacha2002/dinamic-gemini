/*
  0091_client_position_label_hierarchy.sql

  Optional pallet/side/level/marker hierarchy columns on client_position_labels
  for positioning label payload V2.

  Rollback: 0091_client_position_label_hierarchy.down.sql
*/

IF COL_LENGTH(N'dbo.client_position_labels', N'pallet') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD pallet NVARCHAR(64) NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'side') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD side VARCHAR(8) NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'level') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD level INT NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'marker_index') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD marker_index INT NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'marker_total') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD marker_total INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_side'
)
    ALTER TABLE dbo.client_position_labels
        ADD CONSTRAINT CK_client_position_labels_side
        CHECK (side IS NULL OR side IN ('LEFT', 'RIGHT'));
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_level'
)
    ALTER TABLE dbo.client_position_labels
        ADD CONSTRAINT CK_client_position_labels_level
        CHECK (level IS NULL OR level >= 1);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_marker'
)
    ALTER TABLE dbo.client_position_labels
        ADD CONSTRAINT CK_client_position_labels_marker
        CHECK (
            (marker_index IS NULL AND marker_total IS NULL)
            OR (
                marker_index IS NOT NULL
                AND marker_total IS NOT NULL
                AND marker_index >= 1
                AND marker_total >= 1
                AND marker_index <= marker_total
            )
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_client_position_labels_client_hierarchy'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE NONCLUSTERED INDEX IX_client_position_labels_client_hierarchy
        ON dbo.client_position_labels(client_id, pallet, side, level);
GO
