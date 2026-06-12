-- Phase 3.3 — Authoritative finalization stage evidence and artifact manifest
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_finalization_stages')
CREATE TABLE job_finalization_stages (
    job_id VARCHAR(64) NOT NULL,
    stage VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    evidence_level VARCHAR(32) NOT NULL DEFAULT 'unknown',
    completed_at DATETIME2 NULL,
    verified_at DATETIME2 NULL,
    verification_source VARCHAR(128) NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error_code VARCHAR(64) NULL,
    last_error_metadata NVARCHAR(MAX) NULL,
    version INT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_job_finalization_stages PRIMARY KEY (job_id, stage)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_stages_job_id')
    CREATE INDEX IX_job_finalization_stages_job_id ON job_finalization_stages (job_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_stages_status_updated')
    CREATE INDEX IX_job_finalization_stages_status_updated ON job_finalization_stages (status, updated_at);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_artifact_manifest')
CREATE TABLE job_artifact_manifest (
    job_id VARCHAR(64) NOT NULL,
    artifact_kind VARCHAR(64) NOT NULL,
    required BIT NOT NULL DEFAULT 1,
    storage_key VARCHAR(512) NULL,
    content_hash VARCHAR(128) NULL,
    size_bytes BIGINT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    published_at DATETIME2 NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error NVARCHAR(2048) NULL,
    version INT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_job_artifact_manifest PRIMARY KEY (job_id, artifact_kind)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_artifact_manifest_job_id')
    CREATE INDEX IX_job_artifact_manifest_job_id ON job_artifact_manifest (job_id);
GO
