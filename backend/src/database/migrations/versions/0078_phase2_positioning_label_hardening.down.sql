/*
  0078_phase2_positioning_label_hardening.down.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_aisle_location_label_artifacts_status'
)
    ALTER TABLE dbo.aisle_location_label_artifacts
        DROP CONSTRAINT CK_aisle_location_label_artifacts_status;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'render_owner'
)
    ALTER TABLE dbo.aisle_location_label_artifacts DROP COLUMN render_owner;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'updated_at'
)
    ALTER TABLE dbo.aisle_location_label_artifacts DROP COLUMN updated_at;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'failure_detail'
)
    ALTER TABLE dbo.aisle_location_label_artifacts DROP COLUMN failure_detail;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'failure_code'
)
    ALTER TABLE dbo.aisle_location_label_artifacts DROP COLUMN failure_code;
GO

IF EXISTS (
    SELECT 1 FROM sys.objects
    WHERE name = N'DF_aisle_location_label_artifacts_status' AND type = N'D'
)
    ALTER TABLE dbo.aisle_location_label_artifacts
        DROP CONSTRAINT DF_aisle_location_label_artifacts_status;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'status'
)
    ALTER TABLE dbo.aisle_location_label_artifacts DROP COLUMN status;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels') AND name = N'replaced_at'
)
    ALTER TABLE dbo.aisle_location_labels DROP COLUMN replaced_at;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_locations_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    DROP INDEX UQ_aisle_locations_public_identifier ON dbo.aisle_locations;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations') AND name = N'public_identifier'
)
    ALTER TABLE dbo.aisle_locations DROP COLUMN public_identifier;
GO
