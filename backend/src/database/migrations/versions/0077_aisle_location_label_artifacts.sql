/*
  0077_aisle_location_label_artifacts.sql

  Phase 2 — durable rendered positioning label artifacts (PDF/PNG).

  Apply: db_migrate apply / service.apply_pending (UP only).
  Rollback (manual): 0077_aisle_location_label_artifacts.down.sql
*/

IF OBJECT_ID(N'dbo.aisle_location_label_artifacts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.aisle_location_label_artifacts (
        id VARCHAR(36) NOT NULL CONSTRAINT PK_aisle_location_label_artifacts PRIMARY KEY,
        label_id VARCHAR(36) NOT NULL,
        format VARCHAR(16) NOT NULL,
        preset VARCHAR(32) NOT NULL,
        template_version INT NOT NULL,
        marker_version INT NOT NULL,
        storage_provider VARCHAR(32) NOT NULL,
        storage_bucket VARCHAR(255) NULL,
        storage_key VARCHAR(512) NOT NULL,
        content_type VARCHAR(128) NOT NULL,
        file_size_bytes BIGINT NOT NULL,
        artifact_hash VARCHAR(64) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_aisle_location_label_artifacts_label
            FOREIGN KEY (label_id) REFERENCES dbo.aisle_location_labels(id),
        CONSTRAINT CK_aisle_location_label_artifacts_format
            CHECK (format IN (N'PDF', N'PNG')),
        CONSTRAINT CK_aisle_location_label_artifacts_sizes
            CHECK (template_version >= 1 AND marker_version >= 1 AND file_size_bytes >= 0)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_label_artifacts_identity'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_location_label_artifacts_identity
        ON dbo.aisle_location_label_artifacts(
            label_id, format, preset, template_version, marker_version
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_location_label_artifacts_label_created'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
)
    CREATE NONCLUSTERED INDEX IX_aisle_location_label_artifacts_label_created
        ON dbo.aisle_location_label_artifacts(label_id, created_at DESC);
GO
