-- GLOBAL_BATCH durable batch journal (idempotency + crash recovery).
-- Additive + idempotent. Unique natural key: (job_id, execution_id, batch_fingerprint).

IF OBJECT_ID('global_fallback_batch_requests', 'U') IS NULL
BEGIN
    CREATE TABLE global_fallback_batch_requests (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        execution_id VARCHAR(64) NOT NULL,
        attempt INT NOT NULL,
        batch_index INT NOT NULL,
        batch_count INT NOT NULL,
        batch_fingerprint VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        ordered_asset_ids_json NVARCHAR(MAX) NOT NULL,
        provider VARCHAR(128) NOT NULL,
        model VARCHAR(256) NULL,
        schema_version VARCHAR(32) NOT NULL,
        configuration_fingerprint VARCHAR(64) NOT NULL,
        prompt_fingerprint VARCHAR(64) NOT NULL,
        prepared_image_hashes_json NVARCHAR(MAX) NOT NULL,
        provider_request_id VARCHAR(128) NULL,
        response_sha256 VARCHAR(64) NULL,
        normalized_response_json NVARCHAR(MAX) NULL,
        frame_to_asset_map_json NVARCHAR(MAX) NULL,
        merge_plan_json NVARCHAR(MAX) NULL,
        applied_operation_keys_json NVARCHAR(MAX) NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        worker_token VARCHAR(128) NULL,
        estimated_cost FLOAT NULL,
        prompt_tokens INT NULL,
        response_tokens INT NULL,
        duration_ms INT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_global_fallback_batch_requests PRIMARY KEY (id),
        CONSTRAINT CK_gfbr_status CHECK (
            status IN (
                'PREPARED',
                'CALLING',
                'RESPONSE_RECEIVED',
                'VALIDATED',
                'PERSISTING',
                'COMPLETED',
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
    WHERE name = 'UQ_gfbr_job_exec_fingerprint'
      AND object_id = OBJECT_ID('global_fallback_batch_requests')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_gfbr_job_exec_fingerprint
        ON global_fallback_batch_requests(job_id, execution_id, batch_fingerprint);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_gfbr_job_status'
      AND object_id = OBJECT_ID('global_fallback_batch_requests')
)
    CREATE NONCLUSTERED INDEX IX_gfbr_job_status
        ON global_fallback_batch_requests(job_id, status, batch_index);
GO
