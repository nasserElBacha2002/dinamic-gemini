-- Position creation_source (automatic | manual) + unique manual coverage per (job_id, source_asset_id).
-- Additive / idempotent. Does NOT enforce 1:1 image↔position for automatic results.

-- 1) positions.creation_source
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('positions') AND name = 'creation_source'
)
BEGIN
    ALTER TABLE positions ADD creation_source VARCHAR(16) NOT NULL
        CONSTRAINT DF_positions_creation_source DEFAULT 'automatic';
END;
GO

-- Backfill any unexpected NULLs (defensive if column was added differently).
IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('positions') AND name = 'creation_source'
)
BEGIN
    UPDATE positions SET creation_source = 'automatic' WHERE creation_source IS NULL OR LTRIM(RTRIM(creation_source)) = '';
END;
GO

IF OBJECT_ID('positions', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_positions_creation_source'
         AND parent_object_id = OBJECT_ID('positions')
   )
BEGIN
    ALTER TABLE positions
        ADD CONSTRAINT CK_positions_creation_source
        CHECK (creation_source IN ('automatic', 'manual'));
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_positions_job_creation_source'
      AND object_id = OBJECT_ID('positions')
)
    CREATE NONCLUSTERED INDEX IX_positions_job_creation_source
        ON positions(job_id, creation_source)
        WHERE job_id IS NOT NULL;
GO

-- 2) Manual coverage link table — at most one manual result per (job_id, source_asset_id).
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NULL
BEGIN
    CREATE TABLE position_manual_image_coverage (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        created_by_user_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_position_manual_image_coverage PRIMARY KEY (id),
        CONSTRAINT UQ_manual_coverage_job_asset UNIQUE (job_id, source_asset_id),
        CONSTRAINT FK_manual_coverage_position FOREIGN KEY (position_id) REFERENCES positions(id)
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_manual_coverage_position'
      AND object_id = OBJECT_ID('position_manual_image_coverage')
)
    CREATE NONCLUSTERED INDEX IX_manual_coverage_position
        ON position_manual_image_coverage(position_id);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_manual_coverage_job'
      AND object_id = OBJECT_ID('position_manual_image_coverage')
)
    CREATE NONCLUSTERED INDEX IX_manual_coverage_job
        ON position_manual_image_coverage(job_id);
GO

-- 3) Supporting indexes for image↔result resolution (skip if already present).
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_source_assets_job_source_asset'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE NONCLUSTERED INDEX IX_job_source_assets_job_source_asset
        ON job_source_assets(job_id, source_asset_id, position_order);
GO

IF OBJECT_ID('result_evidence', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT * FROM sys.indexes
       WHERE name = 'IX_result_evidence_job_source_asset_id'
         AND object_id = OBJECT_ID('result_evidence')
   )
    CREATE NONCLUSTERED INDEX IX_result_evidence_job_source_asset_id
        ON result_evidence(job_id, source_asset_id);
GO

IF OBJECT_ID('result_evidence', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT * FROM sys.indexes
       WHERE name = 'IX_result_evidence_job_source_image_id'
         AND object_id = OBJECT_ID('result_evidence')
   )
    CREATE NONCLUSTERED INDEX IX_result_evidence_job_source_image_id
        ON result_evidence(job_id, source_image_id);
GO
