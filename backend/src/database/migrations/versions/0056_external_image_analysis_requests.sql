-- Phase 5 corrections — durable external image-analysis request claims (idempotency + recovery).
-- Additive + idempotent. Keep aligned with backend/src/database/schema.sql.
-- Logical identity: (job_id, asset_id, provider, model, prompt_version, configuration_snapshot_version).

IF OBJECT_ID('external_image_analysis_requests', 'U') IS NULL
BEGIN
    CREATE TABLE external_image_analysis_requests (
        id VARCHAR(36) NOT NULL,
        idempotency_key VARCHAR(256) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        provider VARCHAR(128) NOT NULL,
        model VARCHAR(256) NULL,
        prompt_key VARCHAR(128) NULL,
        prompt_version VARCHAR(64) NULL,
        configuration_snapshot_version INT NULL,
        status VARCHAR(32) NOT NULL,
        attempt_id VARCHAR(36) NULL,
        worker_token VARCHAR(128) NULL,
        request_image_sha256 VARCHAR(64) NULL,
        provider_response_sha256 VARCHAR(64) NULL,
        normalized_result_sha256 VARCHAR(64) NULL,
        normalized_result_json NVARCHAR(MAX) NULL,
        validation_result_json NVARCHAR(MAX) NULL,
        usage_json NVARCHAR(MAX) NULL,
        estimated_cost FLOAT NULL,
        duration_ms INT NULL,
        confidence FLOAT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        position_id VARCHAR(36) NULL,
        active_result_id VARCHAR(36) NULL,
        client_id VARCHAR(36) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_external_image_analysis_requests PRIMARY KEY (id),
        CONSTRAINT CK_eiar_status CHECK (
            status IN (
                'CLAIMED',
                'IN_FLIGHT',
                'PROVIDER_SUCCEEDED',
                'VALIDATION_FAILED',
                'PERSISTENCE_PENDING',
                'PERSISTED',
                'FAILED_RETRYABLE',
                'FAILED_FINAL',
                'CANCELLED'
            )
        )
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_eiar_idempotency_key'
      AND object_id = OBJECT_ID('external_image_analysis_requests')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_eiar_idempotency_key
        ON external_image_analysis_requests(idempotency_key);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_eiar_job_asset'
      AND object_id = OBJECT_ID('external_image_analysis_requests')
)
    CREATE NONCLUSTERED INDEX IX_eiar_job_asset
        ON external_image_analysis_requests(job_id, asset_id, created_at);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_eiar_job_status'
      AND object_id = OBJECT_ID('external_image_analysis_requests')
)
    CREATE NONCLUSTERED INDEX IX_eiar_job_status
        ON external_image_analysis_requests(job_id, status);
GO

-- Optional durable bag for attempt lifecycle metadata (provider_call / persistence statuses).
IF COL_LENGTH('processing_attempts', 'extra_json') IS NULL
    ALTER TABLE processing_attempts ADD extra_json NVARCHAR(MAX) NULL;
GO
