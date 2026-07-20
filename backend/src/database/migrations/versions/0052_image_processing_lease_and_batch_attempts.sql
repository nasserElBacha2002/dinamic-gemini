-- Phase 2 corrections — exclusive batch lease + physical batch attempts, and additive
-- worker/lease columns on the Phase 2 (0051) per-asset state and logical attempt tables.
-- Additive only. 0051 is left as-is. Keep aligned with backend/src/database/schema.sql.

-- 1) job_asset_processing_states: worker_token + lease_expires_at (who currently owns the
--    PROCESSING row and when that ownership expires, for abandoned-processing recovery).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_asset_processing_states') AND name = 'worker_token'
)
    ALTER TABLE job_asset_processing_states ADD worker_token VARCHAR(128) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_asset_processing_states') AND name = 'lease_expires_at'
)
    ALTER TABLE job_asset_processing_states ADD lease_expires_at DATETIME2 NULL;
GO

-- 2) processing_attempts: link a logical (per-asset) attempt to the physical batch attempt
--    that produced it, plus the worker that created it and an updated_at audit column.
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('processing_attempts') AND name = 'parent_batch_attempt_id'
)
    ALTER TABLE processing_attempts ADD parent_batch_attempt_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('processing_attempts') AND name = 'batch_execution_id'
)
    ALTER TABLE processing_attempts ADD batch_execution_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('processing_attempts') AND name = 'worker_token'
)
    ALTER TABLE processing_attempts ADD worker_token VARCHAR(128) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('processing_attempts') AND name = 'updated_at'
)
    ALTER TABLE processing_attempts ADD updated_at DATETIME2 NULL;
GO

-- Backfill updated_at for pre-existing rows so the column can be treated as always-populated
-- going forward (application code always writes it on new/updated rows).
UPDATE processing_attempts SET updated_at = created_at WHERE updated_at IS NULL;
GO

-- 3) job_processing_leases — exclusive lease per (job_id, strategy, execution_scope) guarding
--    one physical AISLE_BATCH run at a time across worker processes.
IF OBJECT_ID('job_processing_leases', 'U') IS NULL
BEGIN
    CREATE TABLE job_processing_leases (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        strategy VARCHAR(64) NOT NULL,
        execution_scope VARCHAR(32) NOT NULL,
        status VARCHAR(16) NOT NULL,
        worker_token VARCHAR(128) NULL,
        acquired_at DATETIME2 NULL,
        heartbeat_at DATETIME2 NULL,
        lease_expires_at DATETIME2 NULL,
        released_at DATETIME2 NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        version INT NOT NULL CONSTRAINT DF_jpl_version DEFAULT (1),
        CONSTRAINT PK_job_processing_leases PRIMARY KEY (id),
        CONSTRAINT CK_job_processing_leases_status CHECK (
            status IN ('AVAILABLE', 'ACQUIRED', 'COMPLETED', 'FAILED', 'CANCELLED')
        ),
        CONSTRAINT CK_job_processing_leases_version CHECK (version > 0)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_job_processing_leases_scope'
      AND object_id = OBJECT_ID('job_processing_leases')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_job_processing_leases_scope
        ON job_processing_leases(job_id, strategy, execution_scope);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_processing_leases_expiry'
      AND object_id = OBJECT_ID('job_processing_leases')
)
    CREATE NONCLUSTERED INDEX IX_job_processing_leases_expiry
        ON job_processing_leases(status, lease_expires_at);
GO

-- 4) batch_processing_attempts — one row per physical AISLE_BATCH legacy runner invocation
--    (distinct from processing_attempts, which is logical/per-asset bookkeeping).
IF OBJECT_ID('batch_processing_attempts', 'U') IS NULL
BEGIN
    CREATE TABLE batch_processing_attempts (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        strategy VARCHAR(64) NOT NULL,
        execution_scope VARCHAR(32) NOT NULL,
        provider VARCHAR(128) NULL,
        model VARCHAR(256) NULL,
        prompt_key VARCHAR(128) NULL,
        prompt_version VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL,
        worker_token VARCHAR(128) NULL,
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL,
        duration_ms INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_batch_processing_attempts PRIMARY KEY (id),
        CONSTRAINT CK_batch_processing_attempts_status CHECK (
            status IN ('STARTED', 'SUCCEEDED', 'FAILED_TECHNICAL', 'CANCELLED')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_batch_processing_attempts_job_scope_status'
      AND object_id = OBJECT_ID('batch_processing_attempts')
)
    CREATE NONCLUSTERED INDEX IX_batch_processing_attempts_job_scope_status
        ON batch_processing_attempts(job_id, strategy, execution_scope, status);
GO

-- 5) Value integrity — defensive CHECK constraints for the new nullable columns (idempotent).
IF OBJECT_ID('job_asset_processing_states', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_job_asset_processing_states_worker_token'
         AND parent_object_id = OBJECT_ID('job_asset_processing_states')
   )
BEGIN
    ALTER TABLE job_asset_processing_states
        ADD CONSTRAINT CK_job_asset_processing_states_worker_token
        CHECK (worker_token IS NULL OR LEN(worker_token) > 0);
END;
GO
