/*
  Local CSV import staging + productive results (ingestion channel vs detection source).
  Version 0086 — replaces the misnumbered WIP formerly named 0074_local_csv_imports
  (which collided with 0074_ordered_capture_sessions_and_positioning_foundation).
  Does not create source_assets or fake photos.

  Column types match dbo.inventories(id) / dbo.aisles(id): VARCHAR(36).
*/

IF OBJECT_ID(N'dbo.local_csv_imports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_csv_imports (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        export_id NVARCHAR(255) NOT NULL,
        schema_version NVARCHAR(16) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        device_id NVARCHAR(255) NOT NULL,
        exported_at DATETIME2 NOT NULL,
        status NVARCHAR(32) NOT NULL,
        content_hash NVARCHAR(80) NOT NULL,
        total_rows INT NOT NULL,
        valid_rows INT NOT NULL,
        rejected_rows INT NOT NULL,
        duplicate_rows INT NOT NULL CONSTRAINT DF_local_csv_imports_duplicate_rows DEFAULT 0,
        conflict_policy NVARCHAR(16) NULL,
        confirmed_at DATETIME2 NULL,
        confirmed_by_user_id VARCHAR(128) NULL,
        csv_company_id NVARCHAR(255) NULL,
        csv_client_id NVARCHAR(255) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_local_csv_imports_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT UX_local_csv_imports_inventory_export UNIQUE (inventory_id, export_id),
        CONSTRAINT CK_local_csv_imports_status
            CHECK (status IN ('PREVIEWED', 'CONFIRMED'))
    );
END;
GO

IF OBJECT_ID(N'dbo.local_csv_import_rows', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_csv_import_rows (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        import_id VARCHAR(36) NOT NULL,
        row_number INT NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        capture_session_id NVARCHAR(255) NOT NULL,
        capture_photo_id NVARCHAR(255) NOT NULL,
        client_file_id NVARCHAR(255) NOT NULL,
        capture_order INT NULL,
        captured_at DATETIME2 NULL,
        position_code NVARCHAR(255) NOT NULL,
        internal_code NVARCHAR(255) NULL,
        quantity INT NULL,
        quantity_status NVARCHAR(64) NOT NULL,
        detection_status NVARCHAR(64) NOT NULL,
        -- Detection provenance from CSV column `source` (LOCAL_CODE_SCAN, …).
        detection_source NVARCHAR(64) NOT NULL,
        -- Server-assigned channel; never taken from the client as authoritative.
        ingestion_source NVARCHAR(64) NOT NULL
            CONSTRAINT DF_local_csv_import_rows_ingestion
            DEFAULT N'LOCAL_CSV_IMPORT',
        requires_review BIT NOT NULL,
        error_code NVARCHAR(255) NULL,
        notes NVARCHAR(2000) NULL,
        status NVARCHAR(32) NOT NULL,
        validation_errors_json NVARCHAR(MAX) NOT NULL,
        validation_warnings_json NVARCHAR(MAX) NOT NULL,
        productive_result_id VARCHAR(36) NULL,
        CONSTRAINT FK_local_csv_import_rows_import
            FOREIGN KEY (import_id) REFERENCES dbo.local_csv_imports(id) ON DELETE CASCADE,
        CONSTRAINT UX_local_csv_import_rows_number UNIQUE (import_id, row_number),
        CONSTRAINT CK_local_csv_import_rows_detection_source
            CHECK (detection_source IN (
                N'LOCAL_PENDING',
                N'LOCAL_CODE_SCAN',
                N'LOCAL_MANUAL',
                N'LOCAL_MANUAL_CORRECTION',
                N'LOCAL_POSITION_LABEL',
                N'LOCAL_CODE_SCAN_SHADOW'
            )),
        CONSTRAINT CK_local_csv_import_rows_ingestion_source
            CHECK (ingestion_source = N'LOCAL_CSV_IMPORT'),
        CONSTRAINT CK_local_csv_import_rows_status
            CHECK (status IN ('PREVIEW_VALID', 'REJECTED', 'IMPORTED', 'DUPLICATE', 'REQUIRES_REVIEW'))
    );

    CREATE INDEX IX_local_csv_import_rows_secondary
        ON dbo.local_csv_import_rows(capture_session_id, capture_photo_id, status);

    CREATE UNIQUE INDEX UX_local_csv_import_rows_imported_secondary
        ON dbo.local_csv_import_rows(capture_session_id, capture_photo_id)
        WHERE status = 'IMPORTED';
END;
GO

IF OBJECT_ID(N'dbo.local_csv_productive_results', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_csv_productive_results (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        import_id VARCHAR(36) NOT NULL,
        import_row_id VARCHAR(36) NOT NULL,
        capture_session_id NVARCHAR(255) NOT NULL,
        capture_photo_id NVARCHAR(255) NOT NULL,
        client_file_id NVARCHAR(255) NOT NULL,
        capture_order INT NULL,
        position_code NVARCHAR(255) NULL,
        internal_code NVARCHAR(255) NULL,
        quantity INT NULL,
        quantity_status NVARCHAR(64) NOT NULL,
        detection_status NVARCHAR(64) NOT NULL,
        detection_source NVARCHAR(64) NOT NULL,
        ingestion_source NVARCHAR(64) NOT NULL,
        requires_review BIT NOT NULL,
        has_image_evidence BIT NOT NULL
            CONSTRAINT DF_local_csv_productive_has_image DEFAULT 0,
        confirmed_by_user_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_local_csv_productive_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_local_csv_productive_import
            FOREIGN KEY (import_id) REFERENCES dbo.local_csv_imports(id),
        CONSTRAINT FK_local_csv_productive_row
            FOREIGN KEY (import_row_id) REFERENCES dbo.local_csv_import_rows(id),
        CONSTRAINT UX_local_csv_productive_import_row UNIQUE (import_row_id),
        CONSTRAINT UX_local_csv_productive_secondary UNIQUE (capture_session_id, capture_photo_id),
        CONSTRAINT CK_local_csv_productive_ingestion
            CHECK (ingestion_source = N'LOCAL_CSV_IMPORT'),
        CONSTRAINT CK_local_csv_productive_no_fake_image
            CHECK (has_image_evidence = 0)
    );

    CREATE INDEX IX_local_csv_productive_inventory
        ON dbo.local_csv_productive_results(inventory_id, aisle_id);
END;
GO
