-- Manual coverage integrity: job_source_asset_id NOT NULL + FKs (idempotent).
-- Does not FK source_asset_id (snapshot may outlive deleted source_assets).

-- Step 1: add nullable column if missing
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

-- Step 2: backfill from canonical primary snapshot row
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

-- Step 3: abort if unresolved rows remain before NOT NULL
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND EXISTS (
       SELECT * FROM sys.columns
       WHERE object_id = OBJECT_ID('position_manual_image_coverage')
         AND name = 'job_source_asset_id'
         AND is_nullable = 1
   )
   AND EXISTS (
       SELECT 1
       FROM position_manual_image_coverage
       WHERE job_source_asset_id IS NULL
   )
BEGIN
    THROW 50001,
        'Cannot make job_source_asset_id NOT NULL: unresolved manual coverage rows exist',
        1;
END;
GO

-- Step 4: convert to NOT NULL when still nullable
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND EXISTS (
       SELECT * FROM sys.columns
       WHERE object_id = OBJECT_ID('position_manual_image_coverage')
         AND name = 'job_source_asset_id'
         AND is_nullable = 1
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ALTER COLUMN job_source_asset_id VARCHAR(36) NOT NULL;
END;
GO

-- Drop filtered unique index if present (column is now NOT NULL)
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE name = 'UQ_manual_coverage_job_source_asset'
         AND object_id = OBJECT_ID('position_manual_image_coverage')
         AND has_filter = 1
   )
BEGIN
    DROP INDEX UQ_manual_coverage_job_source_asset ON position_manual_image_coverage;
END;
GO

-- Step 5a: unique index on job_source_asset_id (non-filtered)
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.indexes
       WHERE name = 'UQ_manual_coverage_job_source_asset'
         AND object_id = OBJECT_ID('position_manual_image_coverage')
   )
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_coverage_job_source_asset
        ON position_manual_image_coverage(job_source_asset_id);
END;
GO

-- Pre-FK validation: position_id
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_position'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
   AND EXISTS (
       SELECT 1
       FROM position_manual_image_coverage mic
       LEFT JOIN positions p ON p.id = mic.position_id
       WHERE p.id IS NULL
   )
BEGIN
    THROW 50002, 'Invalid position_id references in manual coverage', 1;
END;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_position'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
BEGIN
    ALTER TABLE position_manual_image_coverage
        ADD CONSTRAINT FK_manual_coverage_position
        FOREIGN KEY (position_id) REFERENCES positions(id);
END;
GO

-- Pre-FK validation: job_id
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_job'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
   AND EXISTS (
       SELECT 1
       FROM position_manual_image_coverage mic
       LEFT JOIN inventory_jobs j ON j.id = mic.job_id
       WHERE j.id IS NULL
   )
BEGIN
    THROW 50002, 'Invalid job_id references in manual coverage', 1;
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

-- Pre-FK validation: aisle_id
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_aisle'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
   AND EXISTS (
       SELECT 1
       FROM position_manual_image_coverage mic
       LEFT JOIN aisles a ON a.id = mic.aisle_id
       WHERE a.id IS NULL
   )
BEGIN
    THROW 50002, 'Invalid aisle_id references in manual coverage', 1;
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

-- Pre-FK validation: inventory_id
IF OBJECT_ID('position_manual_image_coverage', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_manual_coverage_inventory'
         AND parent_object_id = OBJECT_ID('position_manual_image_coverage')
   )
   AND EXISTS (
       SELECT 1
       FROM position_manual_image_coverage mic
       LEFT JOIN inventories i ON i.id = mic.inventory_id
       WHERE i.id IS NULL
   )
BEGIN
    THROW 50002, 'Invalid inventory_id references in manual coverage', 1;
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

-- Pre-FK validation: job_source_asset_id
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
   AND EXISTS (
       SELECT 1
       FROM position_manual_image_coverage mic
       LEFT JOIN job_source_assets jsa ON jsa.id = mic.job_source_asset_id
       WHERE jsa.id IS NULL
   )
BEGIN
    THROW 50002, 'Invalid job_source_asset_id references in manual coverage', 1;
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
