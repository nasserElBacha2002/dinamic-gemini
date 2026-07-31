/*
  0075_phase1_positioning_corrections.sql

  Phase 1 corrections on top of 0074:
  - Label client idempotency columns + filtered unique index
  - One-open-session-per-aisle via filtered unique index on aisle_id
    (status OPEN/UPLOADING only — same exclusion pattern as 0018/0020;
     SQL Server forbids computed columns in filtered-index predicates)
  - Tighten expected_asset_count CHECK (>= 1 when set)
  - Drops obsolete open_aisle_key computed column if a prior failed apply left it

  Apply:
    Run via the UP-only migration runner (db_migrate apply / service.apply_pending).
    Idempotent: IF NOT EXISTS / IF EXISTS guards throughout.

  Rollback (manual, not runner-driven):
    Execute 0075_phase1_positioning_corrections.down.sql against the same DB.
    Drops only 0075 objects; does not reverse 0074.

  Reapply:
    1. Optionally run 0075.down.sql (dev/test only).
    2. Re-run this file (or apply_pending if schema_migrations row was removed).
*/

-- ---------------------------------------------------------------------------
-- 1) aisle_location_labels: client idempotency
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels')
      AND name = N'idempotency_key'
)
    ALTER TABLE dbo.aisle_location_labels ADD idempotency_key VARCHAR(128) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels')
      AND name = N'idempotency_request_hash'
)
    ALTER TABLE dbo.aisle_location_labels ADD idempotency_request_hash VARCHAR(64) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_labels_client_idempotency'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_location_labels_client_idempotency
        ON dbo.aisle_location_labels(client_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
GO

-- ---------------------------------------------------------------------------
-- 2) ordered_capture_sessions: one open/uploading session per aisle
-- ---------------------------------------------------------------------------
-- Remove computed column left by a failed earlier 0075 draft (filter on
-- computed columns is illegal in SQL Server — error 10609).
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
      AND name = N'open_aisle_key'
)
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
          AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
    )
        DROP INDEX UQ_ordered_capture_sessions_one_open_per_aisle
            ON dbo.ordered_capture_sessions;

    ALTER TABLE dbo.ordered_capture_sessions DROP COLUMN open_aisle_key;
END
GO

-- Filtered indexes cannot use IN / OR; exclude terminal/non-open statuses
-- (CHECK constraint limits status to the six known values).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ordered_capture_sessions_one_open_per_aisle
        ON dbo.ordered_capture_sessions(aisle_id)
        WHERE status <> 'SEALED'
          AND status <> 'PROCESSING'
          AND status <> 'COMPLETED'
          AND status <> 'FAILED';
GO

-- ---------------------------------------------------------------------------
-- 3) Tighten CK_ordered_capture_sessions_counts (expected_asset_count >= 1)
-- ---------------------------------------------------------------------------
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
            AND (expected_asset_count IS NULL OR expected_asset_count >= 1)
            AND sequence_version >= 1
        );
GO
