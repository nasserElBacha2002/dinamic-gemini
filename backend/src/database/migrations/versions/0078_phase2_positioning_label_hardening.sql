/*
  0078_phase2_positioning_label_hardening.sql

  Phase 2 corrections:
  - aisle_locations.public_identifier (payload position_id)
  - aisle_location_labels.replaced_at
  - artifact lifecycle status + failure fields
  - nullable storage fields for PENDING reservation

  Rollback: 0078_phase2_positioning_label_hardening.down.sql
*/

-- ---------------------------------------------------------------------------
-- aisle_locations.public_identifier
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations') AND name = N'public_identifier'
)
    ALTER TABLE dbo.aisle_locations ADD public_identifier VARCHAR(64) NULL;
GO

-- Backfill existing rows (stable public ids distinct from internal UUID).
UPDATE dbo.aisle_locations
SET public_identifier = CONCAT(N'loc_', REPLACE(CONVERT(VARCHAR(36), id), N'-', N''))
WHERE public_identifier IS NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations') AND name = N'public_identifier'
)
AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'public_identifier'
      AND is_nullable = 0
)
BEGIN
    ALTER TABLE dbo.aisle_locations ALTER COLUMN public_identifier VARCHAR(64) NOT NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_locations_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_locations_public_identifier
        ON dbo.aisle_locations(public_identifier);
GO

-- ---------------------------------------------------------------------------
-- aisle_location_labels.replaced_at
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels') AND name = N'replaced_at'
)
    ALTER TABLE dbo.aisle_location_labels ADD replaced_at DATETIME2 NULL;
GO

-- ---------------------------------------------------------------------------
-- artifact lifecycle
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'status'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD status VARCHAR(16) NOT NULL
        CONSTRAINT DF_aisle_location_label_artifacts_status DEFAULT (N'READY');
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'failure_code'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD failure_code VARCHAR(64) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'failure_detail'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD failure_detail NVARCHAR(500) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'updated_at'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD updated_at DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'render_owner'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD render_owner VARCHAR(64) NULL;
GO

UPDATE dbo.aisle_location_label_artifacts
SET updated_at = created_at
WHERE updated_at IS NULL;
GO

-- Allow PENDING rows before storage upload completes.
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
      AND name = N'storage_key'
      AND is_nullable = 0
)
    ALTER TABLE dbo.aisle_location_label_artifacts ALTER COLUMN storage_key VARCHAR(512) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_aisle_location_label_artifacts_status'
)
    ALTER TABLE dbo.aisle_location_label_artifacts
        ADD CONSTRAINT CK_aisle_location_label_artifacts_status
        CHECK (status IN (N'PENDING', N'RENDERING', N'READY', N'FAILED'));
GO
