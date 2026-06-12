-- Phase 3.5 corrections — durable staging checksums and due-work indexing
-- SQL Server requires separate batches: ALTER ADD column, then UPDATE referencing it.

IF COL_LENGTH('artifact_publication_outbox', 'source_sha256') IS NULL
    ALTER TABLE artifact_publication_outbox ADD source_sha256 VARCHAR(128) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'storage_etag') IS NULL
    ALTER TABLE artifact_publication_outbox ADD storage_etag VARCHAR(128) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'storage_checksum_value') IS NULL
    ALTER TABLE artifact_publication_outbox ADD storage_checksum_value VARCHAR(128) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'storage_checksum_algorithm') IS NULL
    ALTER TABLE artifact_publication_outbox ADD storage_checksum_algorithm VARCHAR(32) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'verified_at') IS NULL
    ALTER TABLE artifact_publication_outbox ADD verified_at DATETIME2 NULL;
IF COL_LENGTH('artifact_publication_outbox', 'verification_level') IS NULL
    ALTER TABLE artifact_publication_outbox ADD verification_level VARCHAR(32) NULL;
GO

-- Backfill legacy content_hash into source_sha256 when present
UPDATE artifact_publication_outbox
SET source_sha256 = content_hash
WHERE source_sha256 IS NULL AND content_hash IS NOT NULL;
GO

IF COL_LENGTH('job_artifact_manifest', 'source_sha256') IS NULL
    ALTER TABLE job_artifact_manifest ADD source_sha256 VARCHAR(128) NULL;
IF COL_LENGTH('job_artifact_manifest', 'storage_etag') IS NULL
    ALTER TABLE job_artifact_manifest ADD storage_etag VARCHAR(128) NULL;
IF COL_LENGTH('job_artifact_manifest', 'verification_level') IS NULL
    ALTER TABLE job_artifact_manifest ADD verification_level VARCHAR(32) NULL;
IF COL_LENGTH('job_artifact_manifest', 'verified_at') IS NULL
    ALTER TABLE job_artifact_manifest ADD verified_at DATETIME2 NULL;
GO

UPDATE job_artifact_manifest
SET source_sha256 = content_hash
WHERE source_sha256 IS NULL AND content_hash IS NOT NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_artifact_publication_outbox_status')
    ALTER TABLE artifact_publication_outbox ADD CONSTRAINT CK_artifact_publication_outbox_status
        CHECK (status IN ('pending','claimed','published','retry_scheduled','permanently_failed','canceled'));
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_artifact_publication_outbox_source_type')
    ALTER TABLE artifact_publication_outbox ADD CONSTRAINT CK_artifact_publication_outbox_source_type
        CHECK (source_type IN ('exact_durable_source','exact_local_source','reconstructable','unavailable'));
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_due_work')
    CREATE INDEX IX_artifact_publication_outbox_due_work
        ON artifact_publication_outbox (status, next_attempt_at, lease_expires_at)
        INCLUDE (job_id, artifact_kind, version);
GO
