-- Phase 5 corrections: reconciliation identity, lease/retry, revision, FKs.
-- Forward-only additive on 0063. Do not edit 0063 if already applied.
-- Rollback (dev/test): drop new columns/constraints carefully or DROP TABLE.

-- Drop old unique (preliminary + version only) if present.
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'UQ_pdr_preliminary_version'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    ALTER TABLE preliminary_detection_reconciliations
        DROP CONSTRAINT UQ_pdr_preliminary_version;
GO

-- job_id required for identity (backfill empty → keep nullable then constrain new rows in app).
IF COL_LENGTH('preliminary_detection_reconciliations', 'remote_result_fingerprint') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD remote_result_fingerprint VARCHAR(80) NOT NULL
            CONSTRAINT DF_pdr_remote_fp DEFAULT ('PENDING');
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'revision') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD revision INT NOT NULL CONSTRAINT DF_pdr_revision DEFAULT (1);
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'supersedes_id') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD supersedes_id VARCHAR(36) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'row_version') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD row_version INT NOT NULL CONSTRAINT DF_pdr_row_version DEFAULT (1);
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'attempt_count') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD attempt_count INT NOT NULL CONSTRAINT DF_pdr_attempt_count DEFAULT (0);
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'next_retry_at') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD next_retry_at DATETIME2 NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'lease_token') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD lease_token VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'lease_expires_at') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD lease_expires_at DATETIME2 NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'last_error_code') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD last_error_code VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'app_version') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD app_version VARCHAR(32) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'device_model') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD device_model VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'preparation_profile') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD preparation_profile VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'expires_at') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD expires_at DATETIME2 NULL;
GO

-- Identity supporting reprocess: one row per draft + comparison_version + job.
IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'UQ_pdr_preliminary_version_job'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
BEGIN
    -- Normalize NULL job_id for unique (should not happen for new rows).
    UPDATE preliminary_detection_reconciliations
       SET job_id = 'LEGACY-UNKNOWN'
     WHERE job_id IS NULL;

    ALTER TABLE preliminary_detection_reconciliations
        ALTER COLUMN job_id VARCHAR(36) NOT NULL;

    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT UQ_pdr_preliminary_version_job
            UNIQUE (preliminary_detection_id, comparison_version, job_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_pdr_inventory'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT FK_pdr_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_pdr_job'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
) AND OBJECT_ID('inventory_jobs', 'U') IS NOT NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT FK_pdr_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_pdr_not_comparable_reason'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT CK_pdr_not_comparable_reason CHECK (
            (outcome <> 'NOT_COMPARABLE' AND not_comparable_reason IS NULL)
            OR (outcome = 'NOT_COMPARABLE' AND not_comparable_reason IS NOT NULL)
            OR reconciliation_status IN ('PENDING', 'RUNNING', 'RETRY_SCHEDULED')
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_worker_due'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_worker_due
        ON preliminary_detection_reconciliations(reconciliation_status, next_retry_at)
        INCLUDE (lease_expires_at, attempt_count);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_job'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_job
        ON preliminary_detection_reconciliations(job_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_expires'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_expires
        ON preliminary_detection_reconciliations(expires_at)
        WHERE expires_at IS NOT NULL;
GO
