-- Job ↔ source asset snapshot for Observability (historical inputs per job attempt).

IF OBJECT_ID('job_source_assets', 'U') IS NULL
BEGIN
    CREATE TABLE job_source_assets (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        asset_role VARCHAR(32) NOT NULL,
        position_order INT NOT NULL,
        checksum VARCHAR(128) NULL,
        storage_key NVARCHAR(1024) NULL,
        mime_type VARCHAR(255) NULL,
        size_bytes BIGINT NULL,
        width INT NULL,
        height INT NULL,
        stage VARCHAR(64) NULL,
        provider_request_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_job_source_assets PRIMARY KEY (id)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_source_assets_job_order'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE NONCLUSTERED INDEX IX_job_source_assets_job_order
        ON job_source_assets(job_id, position_order, asset_role);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_job_source_assets_job_asset_role'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_job_source_assets_job_asset_role
        ON job_source_assets(job_id, source_asset_id, asset_role);
GO
