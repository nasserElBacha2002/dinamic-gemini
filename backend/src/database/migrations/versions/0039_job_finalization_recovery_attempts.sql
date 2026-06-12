-- Phase 3.4 — Manual finalization recovery audit and lease tracking
-- Foreign keys omitted: job rows may be purged under retention while audit history remains.
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_finalization_recovery_attempts')
CREATE TABLE job_finalization_recovery_attempts (
    id VARCHAR(64) NOT NULL,
    recovery_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    started_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    finished_at DATETIME2 NULL,
    requested_by VARCHAR(128) NOT NULL,
    source VARCHAR(64) NOT NULL,
    initial_assessment_outcome VARCHAR(64) NOT NULL,
    initial_blocking_reason VARCHAR(128) NULL,
    final_assessment_outcome VARCHAR(64) NULL,
    final_blocking_reason VARCHAR(128) NULL,
    error_code VARCHAR(64) NULL,
    sanitized_error NVARCHAR(2048) NULL,
    lease_expires_at DATETIME2 NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_job_finalization_recovery_attempts PRIMARY KEY (id)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_recovery_attempts_job_id')
    CREATE INDEX IX_job_finalization_recovery_attempts_job_id
        ON job_finalization_recovery_attempts (job_id, started_at DESC);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_recovery_attempts_status')
    CREATE INDEX IX_job_finalization_recovery_attempts_status
        ON job_finalization_recovery_attempts (status, lease_expires_at);
GO
