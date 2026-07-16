-- Observability corrections — job_source_assets: original filename + versioned-snapshot metadata.
--
-- source_asset_id remains a HISTORICAL reference only (Strategy Option B): source_assets rows may be
-- deleted (retention, aisle mutation) after a job attempt completes, so no FK is added against
-- source_assets(id). job_source_assets is the durable snapshot of what a job attempt actually used;
-- it must remain readable even if the originating source_assets row is gone.

-- 1) original_filename — display name for Observability input catalog (prefer over storage_key basename).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'original_filename'
)
    ALTER TABLE job_source_assets ADD original_filename NVARCHAR(512) NULL;
GO

-- 2) Optional versioned-snapshot / derived-asset columns (additive, all nullable or defaulted).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'transformation'
)
    ALTER TABLE job_source_assets ADD transformation NVARCHAR(128) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'source_parent_id'
)
    ALTER TABLE job_source_assets ADD source_parent_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'artifact_id'
)
    ALTER TABLE job_source_assets ADD artifact_id VARCHAR(64) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'snapshot_version'
)
    ALTER TABLE job_source_assets ADD snapshot_version INT NOT NULL
        CONSTRAINT DF_job_source_assets_snapshot_version DEFAULT 1;
GO

-- 3) Integrity: job_id -> inventory_jobs(id) ON DELETE CASCADE (job attempt owns its input snapshot).
-- Guarded on inventory_jobs existing so this migration is safe to run against any deployment order.
IF OBJECT_ID('inventory_jobs', 'U') IS NOT NULL
   AND OBJECT_ID('job_source_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_job_source_assets_job'
         AND parent_object_id = OBJECT_ID('job_source_assets')
   )
BEGIN
    ALTER TABLE job_source_assets
        ADD CONSTRAINT FK_job_source_assets_job
        FOREIGN KEY (job_id) REFERENCES inventory_jobs(id) ON DELETE CASCADE;
END;
GO

-- 4) Value integrity — defensive CHECK constraints (idempotent).
IF OBJECT_ID('job_source_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_job_source_assets_position_order'
         AND parent_object_id = OBJECT_ID('job_source_assets')
   )
BEGIN
    ALTER TABLE job_source_assets
        ADD CONSTRAINT CK_job_source_assets_position_order CHECK (position_order >= 0);
END;
GO

IF OBJECT_ID('job_source_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_job_source_assets_size_bytes'
         AND parent_object_id = OBJECT_ID('job_source_assets')
   )
BEGIN
    ALTER TABLE job_source_assets
        ADD CONSTRAINT CK_job_source_assets_size_bytes CHECK (size_bytes IS NULL OR size_bytes >= 0);
END;
GO

-- 5) Query support for versioned snapshots (provider_request_id-scoped lookups). Additive only —
-- the existing UQ_job_source_assets_job_asset_role unique index (job_id, source_asset_id, asset_role)
-- is left untouched to avoid breaking current replace-for-job semantics.
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_source_assets_job_provider_request'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE NONCLUSTERED INDEX IX_job_source_assets_job_provider_request
        ON job_source_assets(job_id, provider_request_id, position_order, asset_role);
GO
