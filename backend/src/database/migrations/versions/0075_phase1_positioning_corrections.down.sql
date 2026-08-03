/*
  0075_phase1_positioning_corrections.down.sql

  Manual rollback for 0075 only (not executed by the UP-only migration runner).

  Reverses:
  - UQ_ordered_capture_sessions_one_open_per_aisle
  - open_aisle_key computed column (if present from a failed draft apply)
  - CK_ordered_capture_sessions_counts → restores 0074 form (expected >= 0)
  - UQ_aisle_location_labels_client_idempotency
  - idempotency_key / idempotency_request_hash columns

  WARNING: DROP COLUMN discards idempotency metadata. This script does not
  preserve that data — fail closed if you need retention (export first).
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    DROP INDEX UQ_ordered_capture_sessions_one_open_per_aisle ON dbo.ordered_capture_sessions;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
      AND name = N'open_aisle_key'
)
    ALTER TABLE dbo.ordered_capture_sessions DROP COLUMN open_aisle_key;
GO

-- Restore 0074 CHECK (expected_asset_count >= 0)
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_ordered_capture_sessions_counts'
      AND parent_object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    ALTER TABLE dbo.ordered_capture_sessions
        DROP CONSTRAINT CK_ordered_capture_sessions_counts;
GO

IF OBJECT_ID(N'dbo.ordered_capture_sessions', N'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_ordered_capture_sessions_counts'
          AND parent_object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
   )
    ALTER TABLE dbo.ordered_capture_sessions
        ADD CONSTRAINT CK_ordered_capture_sessions_counts CHECK (
            uploaded_asset_count >= 0
            AND (expected_asset_count IS NULL OR expected_asset_count >= 0)
            AND sequence_version >= 1
        );
GO

-- Label idempotency index + columns
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_labels_client_idempotency'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    DROP INDEX UQ_aisle_location_labels_client_idempotency ON dbo.aisle_location_labels;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels')
      AND name = N'idempotency_request_hash'
)
    ALTER TABLE dbo.aisle_location_labels DROP COLUMN idempotency_request_hash;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels')
      AND name = N'idempotency_key'
)
    ALTER TABLE dbo.aisle_location_labels DROP COLUMN idempotency_key;
GO
