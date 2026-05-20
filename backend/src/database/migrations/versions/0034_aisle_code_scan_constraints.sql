-- Phase 1 corrections — aisle code scan: one latest run per aisle + enum CHECK constraints.
-- Safe when 0033 was applied without these constraints (idempotent).

-- Replace non-unique latest index with filtered unique index (one is_latest=1 per inventory/aisle).
IF EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_runs_latest' AND object_id = OBJECT_ID('aisle_code_scan_runs')
)
    DROP INDEX IX_aisle_code_scan_runs_latest ON aisle_code_scan_runs;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UX_aisle_code_scan_runs_one_latest' AND object_id = OBJECT_ID('aisle_code_scan_runs')
)
BEGIN
    CREATE UNIQUE INDEX UX_aisle_code_scan_runs_one_latest
    ON aisle_code_scan_runs(inventory_id, aisle_id)
    WHERE is_latest = 1;
END;
GO

-- Run status enum
IF OBJECT_ID('aisle_code_scan_runs', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_runs_status'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_runs')
   )
BEGIN
    ALTER TABLE aisle_code_scan_runs
    ADD CONSTRAINT CK_aisle_code_scan_runs_status CHECK (
        status IN ('running', 'completed', 'completed_with_warnings', 'failed')
    );
END;
GO

-- Detection enums
IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_code_type'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_code_type CHECK (
        code_type IN ('qr', 'barcode', 'datamatrix', 'unknown')
    );
END;
GO

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_detection_status'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_detection_status CHECK (
        detection_status IN ('detected', 'duplicate', 'low_confidence', 'error')
    );
END;
GO
