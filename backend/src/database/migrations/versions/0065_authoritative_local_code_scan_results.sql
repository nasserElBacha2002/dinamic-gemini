-- Intermediate phase: operator-confirmed local CODE_SCAN results (authoritative).
-- Additive / idempotent. Positions are applied at /process via ProcessingResultPersister.
-- Forward-only: disable via SERVER_AUTHORITATIVE_LOCAL_CODE_SCAN_INGEST=false.
-- Formal rollback (dev/test only): DROP TABLE IF EXISTS authoritative_local_code_scan_results;

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_local_code_scan_results (
        id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        client_file_id VARCHAR(36) NOT NULL,
        result_version INT NOT NULL,
        supersedes_result_id VARCHAR(36) NULL,
        is_current BIT NOT NULL CONSTRAINT DF_alcsr_is_current DEFAULT (1),
        internal_code NVARCHAR(64) NOT NULL,
        quantity INT NULL,
        quantity_status VARCHAR(16) NOT NULL,
        source VARCHAR(32) NOT NULL,
        detected_internal_code NVARCHAR(64) NULL,
        detected_quantity INT NULL,
        detected_symbology VARCHAR(32) NULL,
        parser_version VARCHAR(32) NOT NULL,
        detector_version VARCHAR(64) NOT NULL,
        prepared_asset_sha256 VARCHAR(80) NOT NULL,
        content_hash VARCHAR(80) NOT NULL,
        confirmed_by VARCHAR(36) NOT NULL,
        confirmed_at DATETIME2 NOT NULL,
        applied_job_id VARCHAR(36) NULL,
        applied_at DATETIME2 NULL,
        row_version INT NOT NULL CONSTRAINT DF_alcsr_row_version DEFAULT (1),
        schema_version VARCHAR(8) NOT NULL CONSTRAINT DF_alcsr_schema_version DEFAULT ('1'),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_authoritative_local_code_scan_results PRIMARY KEY (id),
        CONSTRAINT UQ_alcsr_asset_version UNIQUE (asset_id, result_version),
        CONSTRAINT FK_alcsr_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_alcsr_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_alcsr_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id),
        CONSTRAINT CK_alcsr_result_version CHECK (result_version >= 1),
        CONSTRAINT CK_alcsr_quantity CHECK (quantity IS NULL OR quantity > 0),
        CONSTRAINT CK_alcsr_quantity_status CHECK (
            quantity_status IN ('PRESENT', 'MISSING')
        ),
        CONSTRAINT CK_alcsr_source CHECK (
            source IN (
                'LOCAL_CODE_SCAN',
                'LOCAL_MANUAL_CORRECTION',
                'SERVER_CODE_SCAN',
                'SERVER_REPROCESS'
            )
        ),
        CONSTRAINT CK_alcsr_qty_consistency CHECK (
            (quantity_status = 'PRESENT' AND quantity IS NOT NULL AND quantity > 0)
            OR (quantity_status = 'MISSING' AND quantity IS NULL)
        )
    );
END
GO

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_alcsr_aisle_current'
          AND object_id = OBJECT_ID('authoritative_local_code_scan_results')
   )
    CREATE INDEX IX_alcsr_aisle_current
        ON authoritative_local_code_scan_results (inventory_id, aisle_id, is_current);
GO

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_alcsr_asset_current'
          AND object_id = OBJECT_ID('authoritative_local_code_scan_results')
   )
    CREATE INDEX IX_alcsr_asset_current
        ON authoritative_local_code_scan_results (asset_id, is_current);
GO

-- Filtered unique: at most one current result per asset (SQL Server filtered index).
IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_alcsr_asset_current'
          AND object_id = OBJECT_ID('authoritative_local_code_scan_results')
   )
    CREATE UNIQUE INDEX UQ_alcsr_asset_current
        ON authoritative_local_code_scan_results (asset_id)
        WHERE is_current = 1;
GO

-- Link preliminary drafts to confirmed authoritative results (historical / diagnostic).
IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NOT NULL
   AND COL_LENGTH('mobile_preliminary_detections', 'confirmed_result_id') IS NULL
BEGIN
    ALTER TABLE mobile_preliminary_detections
        ADD confirmed_result_id VARCHAR(36) NULL;
END
GO

-- Phase 5 reconciliations: leave table; no new auto rows when authoritative path is on.
-- Mark deprecation in application settings / enqueue hook (no DROP).
