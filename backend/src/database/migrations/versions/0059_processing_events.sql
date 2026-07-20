-- Phase 7: structured operational processing events (additive / idempotent).

IF OBJECT_ID('processing_events', 'U') IS NULL
BEGIN
    CREATE TABLE processing_events (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NULL,
        attempt_id VARCHAR(36) NULL,
        event_type VARCHAR(64) NOT NULL,
        severity VARCHAR(16) NOT NULL CONSTRAINT DF_processing_events_severity DEFAULT ('INFO'),
        strategy VARCHAR(64) NULL,
        error_code VARCHAR(128) NULL,
        message NVARCHAR(2000) NULL,
        duration_ms INT NULL,
        correlation_id VARCHAR(64) NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_processing_events PRIMARY KEY (id),
        CONSTRAINT CK_processing_events_severity CHECK (severity IN ('INFO', 'WARN', 'ERROR'))
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_processing_events_job_created'
      AND object_id = OBJECT_ID('processing_events')
)
    CREATE NONCLUSTERED INDEX IX_processing_events_job_created
        ON processing_events(job_id, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_processing_events_job_asset_created'
      AND object_id = OBJECT_ID('processing_events')
)
    CREATE NONCLUSTERED INDEX IX_processing_events_job_asset_created
        ON processing_events(job_id, asset_id, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_processing_events_attempt_created'
      AND object_id = OBJECT_ID('processing_events')
)
    CREATE NONCLUSTERED INDEX IX_processing_events_attempt_created
        ON processing_events(attempt_id, created_at)
        WHERE attempt_id IS NOT NULL;
GO
