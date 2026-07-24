-- Phase 4: mobile preliminary CODE_SCAN drafts (diagnostic only — not authoritative).
-- Additive / idempotent. Does not touch positions, jobs, or final results.
-- Rollback: DROP TABLE IF EXISTS mobile_preliminary_detections;

IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NULL
BEGIN
    CREATE TABLE mobile_preliminary_detections (
        id VARCHAR(36) NOT NULL,
        draft_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        client_file_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        internal_code NVARCHAR(64) NULL,
        quantity INT NULL,
        quantity_status VARCHAR(16) NULL,
        detected_format VARCHAR(32) NULL,
        detected_symbology VARCHAR(32) NULL,
        candidate_count INT NOT NULL CONSTRAINT DF_mpd_candidate_count DEFAULT (0),
        parser_version VARCHAR(32) NOT NULL,
        detector_version VARCHAR(64) NOT NULL,
        prepared_asset_sha256 VARCHAR(80) NOT NULL,
        payload_hash VARCHAR(80) NULL,
        processing_ms INT NULL,
        detected_at DATETIME2 NULL,
        received_at DATETIME2 NOT NULL,
        validation_status VARCHAR(32) NOT NULL,
        validation_error_code VARCHAR(64) NULL,
        schema_version VARCHAR(8) NOT NULL CONSTRAINT DF_mpd_schema_version DEFAULT ('1'),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_mobile_preliminary_detections PRIMARY KEY (id),
        CONSTRAINT UQ_mpd_draft_id UNIQUE (draft_id),
        CONSTRAINT UQ_mpd_client_versions_hash UNIQUE (
            client_file_id, detector_version, parser_version, prepared_asset_sha256
        ),
        CONSTRAINT FK_mpd_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_mpd_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id),
        CONSTRAINT CK_mpd_validation_status CHECK (
            validation_status IN ('PENDING_ASSET', 'RECEIVED', 'VALIDATED', 'REJECTED', 'CONFLICT')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_aisle_received'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_aisle_received
        ON mobile_preliminary_detections(aisle_id, received_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_asset'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_asset
        ON mobile_preliminary_detections(asset_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_client_file'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_client_file
        ON mobile_preliminary_detections(client_file_id);
GO
