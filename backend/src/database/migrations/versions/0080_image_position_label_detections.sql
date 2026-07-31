/*
  0080_image_position_label_detections.sql

  Phase 3 — persist per-image DINAMIC_POSITION detections (no product binding).

  Rollback: 0080_image_position_label_detections.down.sql
*/

IF OBJECT_ID(N'dbo.image_position_label_detections', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.image_position_label_detections (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        client_image_id VARCHAR(64) NULL,
        ordered_capture_session_id VARCHAR(36) NULL,
        sequence_number INT NULL,
        position_label_id VARCHAR(36) NULL,
        public_identifier VARCHAR(64) NULL,
        position_name_snapshot NVARCHAR(200) NULL,
        payload_version INT NULL,
        signature_status VARCHAR(32) NOT NULL,
        detection_status VARCHAR(64) NOT NULL,
        confidence FLOAT NULL,
        bounding_box_json NVARCHAR(MAX) NULL,
        rotation_degrees FLOAT NULL,
        raw_payload_hash VARCHAR(128) NULL,
        detector_name VARCHAR(64) NOT NULL,
        detector_version VARCHAR(64) NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_image_position_label_detections PRIMARY KEY (id),
        CONSTRAINT FK_ipld_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_ipld_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_ipld_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_ipld_asset FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id),
        CONSTRAINT FK_ipld_label FOREIGN KEY (position_label_id) REFERENCES dbo.client_position_labels(id),
        CONSTRAINT CK_ipld_signature_status CHECK (
            signature_status IN ('VALID', 'INVALID', 'MISSING', 'SKIPPED', 'UNKNOWN_KEY')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ipld_asset_detector_hash_status
        ON dbo.image_position_label_detections(
            source_asset_id,
            detector_version,
            detection_status,
            raw_payload_hash
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_job'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_job
        ON dbo.image_position_label_detections(job_id, sequence_number, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_asset'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_asset
        ON dbo.image_position_label_detections(source_asset_id, detection_status);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_label'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_label
        ON dbo.image_position_label_detections(position_label_id)
        WHERE position_label_id IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_client_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_client_status
        ON dbo.image_position_label_detections(client_id, detection_status, created_at DESC);
GO
