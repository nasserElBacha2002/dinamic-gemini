-- Phase 7 corrections: durable asset processing commands + action idempotency.
-- Additive / idempotent for SQL Server.

IF OBJECT_ID('asset_processing_commands', 'U') IS NULL
BEGIN
    CREATE TABLE asset_processing_commands (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        command_type VARCHAR(64) NOT NULL,
        requested_strategy VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL,
        idempotency_key VARCHAR(128) NULL,
        expected_state_version INT NULL,
        actor NVARCHAR(256) NULL,
        reason NVARCHAR(500) NULL,
        payload_json NVARCHAR(MAX) NULL,
        worker_token VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        claimed_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        error_code VARCHAR(128) NULL,
        error_message NVARCHAR(2000) NULL,
        CONSTRAINT PK_asset_processing_commands PRIMARY KEY (id),
        CONSTRAINT CK_apc_status CHECK (
            status IN ('QUEUED', 'CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
        ),
        CONSTRAINT CK_apc_command_type CHECK (
            command_type IN (
                'REPROCESS_FROM_SOURCE',
                'RETRY_PERSISTENCE',
                'SEND_TO_EXTERNAL',
                'RECONCILE_RESULT'
            )
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_apc_job_status_created'
      AND object_id = OBJECT_ID('asset_processing_commands')
)
    CREATE NONCLUSTERED INDEX IX_apc_job_status_created
        ON asset_processing_commands(job_id, status, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_apc_claim_queue'
      AND object_id = OBJECT_ID('asset_processing_commands')
)
    CREATE NONCLUSTERED INDEX IX_apc_claim_queue
        ON asset_processing_commands(status, created_at)
        INCLUDE (job_id, asset_id, command_type)
        WHERE status = 'QUEUED';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_apc_job_asset_created'
      AND object_id = OBJECT_ID('asset_processing_commands')
)
    CREATE NONCLUSTERED INDEX IX_apc_job_asset_created
        ON asset_processing_commands(job_id, asset_id, created_at DESC);
GO

IF OBJECT_ID('processing_action_idempotency', 'U') IS NULL
BEGIN
    CREATE TABLE processing_action_idempotency (
        id VARCHAR(36) NOT NULL,
        action_type VARCHAR(64) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        response_json NVARCHAR(MAX) NOT NULL,
        status VARCHAR(32) NOT NULL,
        state_version INT NULL,
        actor NVARCHAR(256) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_processing_action_idempotency PRIMARY KEY (id),
        CONSTRAINT UQ_pai_action_scope_key UNIQUE (action_type, job_id, asset_id, idempotency_key)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pai_job_asset'
      AND object_id = OBJECT_ID('processing_action_idempotency')
)
    CREATE NONCLUSTERED INDEX IX_pai_job_asset
        ON processing_action_idempotency(job_id, asset_id, created_at DESC);
GO

-- Read-model helpers for operational list (filtered indexes when tables exist).
IF OBJECT_ID('job_asset_processing_states', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_japs_job_status_updated'
          AND object_id = OBJECT_ID('job_asset_processing_states')
   )
    CREATE NONCLUSTERED INDEX IX_japs_job_status_updated
        ON job_asset_processing_states(job_id, status, updated_at DESC);
GO

IF OBJECT_ID('processing_attempts', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pa_job_asset_finished'
          AND object_id = OBJECT_ID('processing_attempts')
   )
    CREATE NONCLUSTERED INDEX IX_pa_job_asset_finished
        ON processing_attempts(job_id, asset_id, finished_at DESC, attempt_number DESC);
GO
