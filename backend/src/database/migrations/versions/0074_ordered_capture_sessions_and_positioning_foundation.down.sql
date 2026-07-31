/*
  0074_ordered_capture_sessions_and_positioning_foundation.down.sql

  Manual rollback for 0074 (not executed by the UP-only migration runner).

  Drop order (safe):
  1. Filtered unique / supporting indexes
  2. FKs into ordered_capture_sessions
  3. CHECKs on source_assets
  4. Tables: aisle_location_labels → aisle_locations → ordered_capture_sessions
  5. Columns on source_assets / inventory_jobs / job_source_assets

  WARNING: This is destructive. It DROPs tables and columns introduced by 0074
  (and any 0075 columns that still hang off those tables). It does NOT preserve
  data. If you need retention, export first and stop — this script fails closed
  by design (no soft-delete / archive path). Re-run 0074 (+ 0075) to restore DDL.
*/

-- ---------------------------------------------------------------------------
-- 1) Indexes that reference Phase 1 columns / tables
-- ---------------------------------------------------------------------------
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_labels_client_idempotency'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    DROP INDEX UQ_aisle_location_labels_client_idempotency ON dbo.aisle_location_labels;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_labels_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    DROP INDEX UQ_aisle_location_labels_public_identifier ON dbo.aisle_location_labels;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_location_labels_location_status'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    DROP INDEX IX_aisle_location_labels_location_status ON dbo.aisle_location_labels;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_locations_client_aisle_normalized_code_active'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    DROP INDEX UQ_aisle_locations_client_aisle_normalized_code_active ON dbo.aisle_locations;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_locations_aisle_status'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    DROP INDEX IX_aisle_locations_aisle_status ON dbo.aisle_locations;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    DROP INDEX UQ_ordered_capture_sessions_one_open_per_aisle ON dbo.ordered_capture_sessions;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ordered_capture_sessions_aisle_status'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    DROP INDEX IX_ordered_capture_sessions_aisle_status ON dbo.ordered_capture_sessions;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ordered_capture_sessions_inventory'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    DROP INDEX IX_ordered_capture_sessions_inventory ON dbo.ordered_capture_sessions;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_source_assets_ordered_session_sequence'
      AND object_id = OBJECT_ID(N'dbo.source_assets')
)
    DROP INDEX UQ_source_assets_ordered_session_sequence ON dbo.source_assets;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_source_assets_ordered_session_client_file'
      AND object_id = OBJECT_ID(N'dbo.source_assets')
)
    DROP INDEX UQ_source_assets_ordered_session_client_file ON dbo.source_assets;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_source_assets_ordered_session_sequence'
      AND object_id = OBJECT_ID(N'dbo.source_assets')
)
    DROP INDEX IX_source_assets_ordered_session_sequence ON dbo.source_assets;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_inventory_jobs_ordered_session_version'
      AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
)
    DROP INDEX UQ_inventory_jobs_ordered_session_version ON dbo.inventory_jobs;
GO

-- ---------------------------------------------------------------------------
-- 2) Foreign keys into ordered_capture_sessions
-- ---------------------------------------------------------------------------
IF EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_source_assets_ordered_capture_session'
)
    ALTER TABLE dbo.source_assets DROP CONSTRAINT FK_source_assets_ordered_capture_session;
GO

IF EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_inventory_jobs_ordered_capture_session'
)
    ALTER TABLE dbo.inventory_jobs DROP CONSTRAINT FK_inventory_jobs_ordered_capture_session;
GO

-- ---------------------------------------------------------------------------
-- 3) CHECKs on source_assets (Phase 1)
-- ---------------------------------------------------------------------------
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_source_assets_sequence_source'
)
    ALTER TABLE dbo.source_assets DROP CONSTRAINT CK_source_assets_sequence_source;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_source_assets_sequence_number_positive'
)
    ALTER TABLE dbo.source_assets DROP CONSTRAINT CK_source_assets_sequence_number_positive;
GO

-- ---------------------------------------------------------------------------
-- 4) Tables (labels → locations → sessions)
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.aisle_location_labels', N'U') IS NOT NULL
    DROP TABLE dbo.aisle_location_labels;
GO

IF OBJECT_ID(N'dbo.aisle_locations', N'U') IS NOT NULL
    DROP TABLE dbo.aisle_locations;
GO

IF OBJECT_ID(N'dbo.ordered_capture_sessions', N'U') IS NOT NULL
    DROP TABLE dbo.ordered_capture_sessions;
GO

-- ---------------------------------------------------------------------------
-- 5) Columns on existing tables
-- ---------------------------------------------------------------------------
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'ordered_capture_session_id'
)
    ALTER TABLE dbo.source_assets DROP COLUMN ordered_capture_session_id;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'sequence_number'
)
    ALTER TABLE dbo.source_assets DROP COLUMN sequence_number;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'sequence_source'
)
    ALTER TABLE dbo.source_assets DROP COLUMN sequence_source;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_jobs') AND name = N'ordered_capture_session_id'
)
    ALTER TABLE dbo.inventory_jobs DROP COLUMN ordered_capture_session_id;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_jobs') AND name = N'sequence_version'
)
    ALTER TABLE dbo.inventory_jobs DROP COLUMN sequence_version;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.job_source_assets') AND name = N'sequence_number'
)
    ALTER TABLE dbo.job_source_assets DROP COLUMN sequence_number;
GO
