-- Phase 5: preliminary vs remote reconciliation (diagnostic only).
-- Forward-only. Disable via SERVER_PRELIMINARY_RECONCILIATION=false.
-- Rollback (dev/test): DROP TABLE IF EXISTS preliminary_detection_reconciliations;

IF OBJECT_ID('preliminary_detection_reconciliations', 'U') IS NULL
BEGIN
    CREATE TABLE preliminary_detection_reconciliations (
        id VARCHAR(36) NOT NULL,
        preliminary_detection_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        remote_result_id VARCHAR(36) NULL,
        job_id VARCHAR(36) NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        client_file_id VARCHAR(36) NOT NULL,
        local_status VARCHAR(32) NOT NULL,
        local_internal_code NVARCHAR(64) NULL,
        local_quantity INT NULL,
        remote_status VARCHAR(32) NULL,
        remote_internal_code NVARCHAR(64) NULL,
        remote_quantity INT NULL,
        outcome VARCHAR(64) NOT NULL,
        not_comparable_reason VARCHAR(64) NULL,
        local_parser_version VARCHAR(32) NULL,
        local_detector_version VARCHAR(64) NULL,
        remote_pipeline_version VARCHAR(64) NULL,
        local_detected_at DATETIME2 NULL,
        remote_completed_at DATETIME2 NULL,
        compared_at DATETIME2 NOT NULL,
        comparison_version VARCHAR(16) NOT NULL,
        reconciliation_status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_preliminary_detection_reconciliations PRIMARY KEY (id),
        CONSTRAINT UQ_pdr_preliminary_version UNIQUE (preliminary_detection_id, comparison_version),
        CONSTRAINT FK_pdr_preliminary FOREIGN KEY (preliminary_detection_id)
            REFERENCES mobile_preliminary_detections(id),
        CONSTRAINT FK_pdr_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id),
        CONSTRAINT FK_pdr_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_pdr_reconciliation_status CHECK (
            reconciliation_status IN (
                'PENDING', 'RUNNING', 'COMPLETED', 'NOT_COMPARABLE',
                'RETRY_SCHEDULED', 'FAILED_TERMINAL'
            )
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_inventory_aisle'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_inventory_aisle
        ON preliminary_detection_reconciliations(inventory_id, aisle_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_aisle_compared'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_aisle_compared
        ON preliminary_detection_reconciliations(aisle_id, compared_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_asset'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_asset
        ON preliminary_detection_reconciliations(asset_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_outcome'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_outcome
        ON preliminary_detection_reconciliations(outcome);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_client_file'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_client_file
        ON preliminary_detection_reconciliations(client_file_id);
GO
