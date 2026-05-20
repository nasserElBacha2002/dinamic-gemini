-- Phase 1 — Aisle QR/barcode code scan runs and detections (auxiliary flow; independent of AI worker).

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'aisle_code_scan_runs')
BEGIN
    CREATE TABLE aisle_code_scan_runs (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        total_assets INT NOT NULL,
        processed_assets INT NOT NULL,
        failed_assets INT NOT NULL,
        total_codes_found INT NOT NULL,
        total_qr_found INT NOT NULL,
        total_barcodes_found INT NOT NULL,
        started_at DATETIME2 NOT NULL,
        finished_at DATETIME2 NULL,
        error_message NVARCHAR(2048) NULL,
        scanner_engine VARCHAR(64) NOT NULL,
        is_latest BIT NOT NULL CONSTRAINT DF_aisle_code_scan_runs_is_latest DEFAULT 0,
        created_by VARCHAR(128) NULL,
        metadata_json NVARCHAR(MAX) NULL,
        CONSTRAINT FK_aisle_code_scan_runs_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aisle_code_scan_runs_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_aisle_code_scan_runs_inventory_aisle ON aisle_code_scan_runs(inventory_id, aisle_id);
    CREATE INDEX IX_aisle_code_scan_runs_aisle_started ON aisle_code_scan_runs(aisle_id, started_at);
    CREATE INDEX IX_aisle_code_scan_runs_latest ON aisle_code_scan_runs(inventory_id, aisle_id, is_latest);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'aisle_code_scan_detections')
BEGIN
    CREATE TABLE aisle_code_scan_detections (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        run_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        code_type VARCHAR(16) NOT NULL,
        code_value NVARCHAR(2048) NOT NULL,
        normalized_code_value NVARCHAR(2048) NOT NULL,
        bounding_box_json NVARCHAR(MAX) NULL,
        confidence FLOAT NULL,
        detection_status VARCHAR(32) NOT NULL,
        scanner_engine VARCHAR(64) NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_aisle_code_scan_detections_run FOREIGN KEY (run_id) REFERENCES aisle_code_scan_runs(id),
        CONSTRAINT FK_aisle_code_scan_detections_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aisle_code_scan_detections_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_aisle_code_scan_detections_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_aisle_code_scan_detections_run ON aisle_code_scan_detections(run_id);
    CREATE INDEX IX_aisle_code_scan_detections_asset ON aisle_code_scan_detections(asset_id);
    CREATE INDEX IX_aisle_code_scan_detections_aisle_norm ON aisle_code_scan_detections(aisle_id, normalized_code_value);
    CREATE INDEX IX_aisle_code_scan_detections_scope ON aisle_code_scan_detections(inventory_id, aisle_id);
END;
GO
