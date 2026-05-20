-- Phase 4 — read-only code scan matching fields on detections (audit snapshot).

IF COL_LENGTH('aisle_code_scan_detections', 'matched_position_id') IS NULL
BEGIN
    ALTER TABLE aisle_code_scan_detections ADD matched_position_id VARCHAR(36) NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_status VARCHAR(32) NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_type VARCHAR(64) NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_confidence FLOAT NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_metadata_json NVARCHAR(MAX) NULL;
    ALTER TABLE aisle_code_scan_detections ADD matched_at DATETIME2 NULL;
END;
GO

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_aisle_code_scan_detections_matched_position'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT FK_aisle_code_scan_detections_matched_position
        FOREIGN KEY (matched_position_id) REFERENCES positions(id);
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_detections_aisle_match_status'
      AND object_id = OBJECT_ID('aisle_code_scan_detections')
)
    CREATE INDEX IX_aisle_code_scan_detections_aisle_match_status
    ON aisle_code_scan_detections(aisle_id, match_status);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_detections_aisle_matched_position'
      AND object_id = OBJECT_ID('aisle_code_scan_detections')
)
    CREATE INDEX IX_aisle_code_scan_detections_aisle_matched_position
    ON aisle_code_scan_detections(aisle_id, matched_position_id);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_detections_run_match_status'
      AND object_id = OBJECT_ID('aisle_code_scan_detections')
)
    CREATE INDEX IX_aisle_code_scan_detections_run_match_status
    ON aisle_code_scan_detections(run_id, match_status);
GO
