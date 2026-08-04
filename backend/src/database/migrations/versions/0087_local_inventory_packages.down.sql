/*
  Rollback 0087_local_inventory_packages.
  Drops package tables, then restores CSV-only image-evidence constraint.
  Note: rows with has_image_evidence=1 must be cleared before restoring the old CHECK.
*/

IF OBJECT_ID(N'dbo.local_inventory_package_photos', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.local_inventory_package_photos;
END;
GO

IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.local_inventory_packages;
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = N'FK_local_csv_productive_source_asset'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT FK_local_csv_productive_source_asset;
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_image_evidence'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT CK_local_csv_productive_image_evidence;
END;
GO

UPDATE dbo.local_csv_productive_results
SET has_image_evidence = 0, source_asset_id = NULL
WHERE has_image_evidence = 1 OR source_asset_id IS NOT NULL;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'source_asset_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results DROP COLUMN source_asset_id;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_no_fake_image'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT CK_local_csv_productive_no_fake_image
        CHECK (has_image_evidence = 0);
END;
GO
