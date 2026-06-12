-- Phase 3.5 — Durable artifact publication outbox
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'artifact_publication_outbox')
CREATE TABLE artifact_publication_outbox (
    id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    artifact_kind VARCHAR(64) NOT NULL,
    required BIT NOT NULL DEFAULT 1,
    source_type VARCHAR(64) NOT NULL DEFAULT 'exact_local_source',
    source_reference NVARCHAR(1024) NULL,
    destination_key VARCHAR(512) NULL,
    content_hash VARCHAR(128) NULL,
    size_bytes BIGINT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at DATETIME2 NULL,
    claimed_at DATETIME2 NULL,
    claimed_by VARCHAR(128) NULL,
    lease_expires_at DATETIME2 NULL,
    last_error_code VARCHAR(64) NULL,
    last_error_message NVARCHAR(2048) NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    published_at DATETIME2 NULL,
    version INT NOT NULL DEFAULT 1,
    CONSTRAINT PK_artifact_publication_outbox PRIMARY KEY (id),
    CONSTRAINT UQ_artifact_publication_outbox_job_kind UNIQUE (job_id, artifact_kind),
    CONSTRAINT CK_artifact_publication_outbox_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT CK_artifact_publication_outbox_max_attempts CHECK (max_attempts > 0),
    CONSTRAINT CK_artifact_publication_outbox_version CHECK (version > 0),
    CONSTRAINT CK_artifact_publication_outbox_size_bytes CHECK (size_bytes IS NULL OR size_bytes >= 0)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_status_next')
    CREATE INDEX IX_artifact_publication_outbox_status_next
        ON artifact_publication_outbox (status, next_attempt_at);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_job_id')
    CREATE INDEX IX_artifact_publication_outbox_job_id
        ON artifact_publication_outbox (job_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_lease_expires')
    CREATE INDEX IX_artifact_publication_outbox_lease_expires
        ON artifact_publication_outbox (lease_expires_at);
GO
