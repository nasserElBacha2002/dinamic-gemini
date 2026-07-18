-- Phase 2 — per-asset processing state + processing attempts (additive).
-- Logical bookkeeping around AISLE_BATCH legacy execution.
-- Keep aligned with backend/src/database/schema.sql.

IF OBJECT_ID('job_asset_processing_states', 'U') IS NULL
BEGIN
    CREATE TABLE job_asset_processing_states (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        active_result_id VARCHAR(36) NULL,
        attempt_count INT NOT NULL CONSTRAINT DF_japs_attempt_count DEFAULT (0),
        last_strategy VARCHAR(64) NULL,
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL,
        duration_ms INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        version INT NOT NULL CONSTRAINT DF_japs_version DEFAULT (1),
        execution_scope VARCHAR(32) NULL,
        CONSTRAINT PK_job_asset_processing_states PRIMARY KEY (id),
        CONSTRAINT CK_job_asset_processing_states_status CHECK (
            status IN (
                'PENDING', 'PROCESSING', 'RESOLVED', 'UNRECOGNIZED',
                'FAILED_TECHNICAL', 'PENDING_MANUAL_REVIEW', 'CANCELLED'
            )
        ),
        CONSTRAINT CK_job_asset_processing_states_version CHECK (version > 0),
        CONSTRAINT CK_job_asset_processing_states_attempt_count CHECK (attempt_count >= 0)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_job_asset_processing_states_job_asset'
      AND object_id = OBJECT_ID('job_asset_processing_states')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_job_asset_processing_states_job_asset
        ON job_asset_processing_states(job_id, asset_id);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_asset_processing_states_job_status'
      AND object_id = OBJECT_ID('job_asset_processing_states')
)
    CREATE NONCLUSTERED INDEX IX_job_asset_processing_states_job_status
        ON job_asset_processing_states(job_id, status);
GO

IF OBJECT_ID('processing_attempts', 'U') IS NULL
BEGIN
    CREATE TABLE processing_attempts (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        strategy VARCHAR(64) NOT NULL,
        provider VARCHAR(128) NULL,
        model VARCHAR(256) NULL,
        status VARCHAR(32) NOT NULL,
        attempt_number INT NOT NULL,
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL,
        duration_ms INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        raw_result_reference NVARCHAR(1024) NULL,
        normalized_result_json NVARCHAR(MAX) NULL,
        validation_result_json NVARCHAR(MAX) NULL,
        execution_scope VARCHAR(32) NULL,
        logical_asset_attempt BIT NOT NULL CONSTRAINT DF_pa_logical DEFAULT (1),
        configuration_snapshot_version INT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_processing_attempts PRIMARY KEY (id),
        CONSTRAINT CK_processing_attempts_status CHECK (
            status IN (
                'STARTED', 'SUCCEEDED', 'INVALID', 'UNRECOGNIZED',
                'FAILED_TECHNICAL', 'CANCELLED'
            )
        ),
        CONSTRAINT CK_processing_attempts_attempt_number CHECK (attempt_number > 0)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_processing_attempts_job_asset_strategy_n'
      AND object_id = OBJECT_ID('processing_attempts')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_processing_attempts_job_asset_strategy_n
        ON processing_attempts(job_id, asset_id, strategy, attempt_number);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_processing_attempts_job_asset'
      AND object_id = OBJECT_ID('processing_attempts')
)
    CREATE NONCLUSTERED INDEX IX_processing_attempts_job_asset
        ON processing_attempts(job_id, asset_id, attempt_number);
GO
