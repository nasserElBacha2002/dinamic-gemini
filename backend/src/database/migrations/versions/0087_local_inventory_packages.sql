/*
  Local inventory ZIP package import + productive image evidence.
  Version 0087.

  - Relaxes CK_local_csv_productive_no_fake_image so package imports may set
    has_image_evidence=1 with source_asset_id.
  - Adds staging tables for package preview/confirm.
*/

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'source_asset_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD source_asset_id VARCHAR(36) NULL;
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_no_fake_image'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT CK_local_csv_productive_no_fake_image;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_image_evidence'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT CK_local_csv_productive_image_evidence
        CHECK (
            (has_image_evidence = 0 AND source_asset_id IS NULL)
            OR (has_image_evidence = 1 AND source_asset_id IS NOT NULL)
        );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = N'FK_local_csv_productive_source_asset'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT FK_local_csv_productive_source_asset
        FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id);
END;
GO

IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_inventory_packages (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        export_id NVARCHAR(255) NOT NULL,
        csv_import_id VARCHAR(36) NOT NULL,
        package_kind NVARCHAR(64) NOT NULL,
        package_version INT NOT NULL,
        status NVARCHAR(32) NOT NULL,
        package_checksum_sha256 NVARCHAR(80) NULL,
        csv_checksum_sha256 NVARCHAR(80) NOT NULL,
        expected_photo_count INT NOT NULL,
        included_photo_count INT NOT NULL,
        aisle_id VARCHAR(36) NULL,
        capture_session_id NVARCHAR(255) NULL,
        freeze_id NVARCHAR(255) NULL,
        staging_dir NVARCHAR(1024) NOT NULL,
        confirmed_at DATETIME2 NULL,
        confirmed_by_user_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_local_inventory_packages_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_local_inventory_packages_csv_import
            FOREIGN KEY (csv_import_id) REFERENCES dbo.local_csv_imports(id),
        CONSTRAINT UX_local_inventory_packages_inventory_export
            UNIQUE (inventory_id, export_id),
        CONSTRAINT CK_local_inventory_packages_status
            CHECK (status IN ('PREVIEWED', 'CONFIRMED'))
    );
END;
GO

IF OBJECT_ID(N'dbo.local_inventory_package_photos', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_inventory_package_photos (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        package_id VARCHAR(36) NOT NULL,
        capture_photo_id NVARCHAR(255) NOT NULL,
        client_file_id NVARCHAR(255) NOT NULL,
        sequence_number INT NULL,
        file_name NVARCHAR(255) NOT NULL,
        mime_type NVARCHAR(128) NOT NULL,
        size_bytes INT NOT NULL,
        sha256 NVARCHAR(80) NOT NULL,
        width INT NULL,
        height INT NULL,
        asset_variant NVARCHAR(32) NOT NULL,
        staging_path NVARCHAR(1024) NOT NULL,
        source_asset_id VARCHAR(36) NULL,
        CONSTRAINT FK_local_inventory_package_photos_package
            FOREIGN KEY (package_id) REFERENCES dbo.local_inventory_packages(id) ON DELETE CASCADE,
        CONSTRAINT UX_local_inventory_package_photos_capture
            UNIQUE (package_id, capture_photo_id)
    );
END;
GO
