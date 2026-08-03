/*
  0077_aisle_location_label_artifacts.down.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_location_label_artifacts_label_created'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
)
    DROP INDEX IX_aisle_location_label_artifacts_label_created ON dbo.aisle_location_label_artifacts;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_label_artifacts_identity'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
)
    DROP INDEX UQ_aisle_location_label_artifacts_identity ON dbo.aisle_location_label_artifacts;
GO

IF OBJECT_ID(N'dbo.aisle_location_label_artifacts', N'U') IS NOT NULL
    DROP TABLE dbo.aisle_location_label_artifacts;
GO
