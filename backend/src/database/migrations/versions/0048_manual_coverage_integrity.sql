-- Manual coverage integrity: job_source_asset_id + FKs (idempotent).
-- Does not FK source_asset_id (snapshot may outlive deleted source_assets).

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT * FROM sys.columns
       WHERE object_id = OBJECT_ID('position_manual_image_coverage')
         AND name = 'job_source_asset_id'
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ADD job_source_asset_id VARCHAR(36) NULL;
END;
GO

-- Backfill job_source_asset_id from canonical primary snapshot row per (job_id, source_asset_id).
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND EXISTS (
       SELECT * FROM sys.columns
       WHERE object_id = OBJECT_ID('position_manual_image_coverage')
         AND name = 'job_source_asset_id'
   )
BEGIN
    UPDATE mic
    SET mic.job_source_asset_id = jsa.id
    FROM position_manual_image_coverage mic
    INNER JOIN (
        SELECT jsa2.id, jsa2.job_id, jsa2.source_asset_id,
               ROW_NUMBER() OVER (
                   PARTITION BY jsa2.job_id, jsa2.source_asset_id
                   ORDER BY jsa2.position_order, jsa2.id
               ) AS rn
        FROM job_source_assets jsa2
        WHERE LOWER(LTRIM(RTRIM(ISNULL(jsa2.asset_role, '')))) = 'primary'
    ) jsa
        ON jsa.job_id = mic.job_id
       AND jsa.source_asset_id = mic.source_asset_id
       AND jsa.rn = 1
    WHERE mic.job_source_asset_id IS NULL;
END;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE name = 'UQ_manual_coverage_job_source_asset'
         AND object_id = OBJECT_ID('position_manual_image_coverage')
   )
   AND EXISTS (
       SELECT * FROM sys.columns
       WHERE object_id = OBJECT_ID('position_manual_image_coverage')
         AND name = 'job_source_asset_id'
   )
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_coverage_job_source_asset
        ON position_manual_image_coverage(job_source_asset_id)
        WHERE job_source_asset_id IS NOT NULL;
END;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_job'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ADD CONSTRAINT FK_manual_coverage_job
        FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_aisle'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ADD CONSTRAINT FK_manual_coverage_aisle
        FOREIGN KEY (aisle_id) REFERENCES aisles(id);
END;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_inventory'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ADD CONSTRAINT FK_manual_coverage_inventory
        FOREIGN KEY (inventory_id) REFERENCES inventories(id);
END;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_job_source_asset'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
   AND EXISTS (
       SELECT * FROM sys.columns
       WHERE object_id = OBJECT_ID('position_manual_image_coverage')
         AND name = 'job_source_asset_id'
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ADD CONSTRAINT FK_manual_coverage_job_source_asset
        FOREIGN KEY (job_source_asset_id) REFERENCES job_source_assets(id);
END;
GO
