/*
  Phase 5 local CSV import audit and row-result persistence.
  Capture photo identifiers remain external evidence references; this migration does not
  create or link source_assets.
*/

IF OBJECT_ID(N'dbo.local_csv_imports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_csv_imports (
        id NVARCHAR(64) NOT NULL PRIMARY KEY,
        export_id NVARCHAR(255) NOT NULL,
        schema_version NVARCHAR(16) NOT NULL,
        inventory_id NVARCHAR(64) NOT NULL,
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
        id NVARCHAR(64) NOT NULL PRIMARY KEY,
        import_id NVARCHAR(64) NOT NULL,
        row_number INT NOT NULL,
        inventory_id NVARCHAR(64) NOT NULL,
        aisle_id NVARCHAR(64) NOT NULL,
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
        source NVARCHAR(64) NOT NULL,
        requires_review BIT NOT NULL,
        error_code NVARCHAR(255) NULL,
        notes NVARCHAR(2000) NULL,
        status NVARCHAR(32) NOT NULL,
        validation_errors_json NVARCHAR(MAX) NOT NULL,
        validation_warnings_json NVARCHAR(MAX) NOT NULL,
        CONSTRAINT FK_local_csv_import_rows_import
            FOREIGN KEY (import_id) REFERENCES dbo.local_csv_imports(id) ON DELETE CASCADE,
        CONSTRAINT UX_local_csv_import_rows_number UNIQUE (import_id, row_number),
        CONSTRAINT CK_local_csv_import_rows_source CHECK (source = 'LOCAL_CSV_IMPORT'),
        CONSTRAINT CK_local_csv_import_rows_status
            CHECK (status IN ('PREVIEW_VALID', 'REJECTED', 'IMPORTED', 'DUPLICATE'))
    );

    CREATE INDEX IX_local_csv_import_rows_secondary
        ON dbo.local_csv_import_rows(capture_session_id, capture_photo_id, status);

    CREATE UNIQUE INDEX UX_local_csv_import_rows_imported_secondary
        ON dbo.local_csv_import_rows(capture_session_id, capture_photo_id)
        WHERE status = 'IMPORTED';
END;
GO
