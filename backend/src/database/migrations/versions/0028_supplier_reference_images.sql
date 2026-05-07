-- Phase C1 — supplier-level reference images foundation (additive only).

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'supplier_reference_images')
BEGIN
    CREATE TABLE supplier_reference_images (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        client_supplier_id VARCHAR(36) NOT NULL,
        filename NVARCHAR(512) NOT NULL,
        storage_path NVARCHAR(1024) NOT NULL,
        storage_provider VARCHAR(16) NULL,
        storage_bucket NVARCHAR(255) NULL,
        storage_key NVARCHAR(1024) NULL,
        content_type VARCHAR(128) NULL,
        file_size_bytes BIGINT NULL,
        etag NVARCHAR(128) NULL,
        mime_type VARCHAR(128) NOT NULL,
        file_size BIGINT NOT NULL,
        label NVARCHAR(255) NULL,
        description NVARCHAR(1024) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_supplier_reference_images_client_supplier
            FOREIGN KEY (client_supplier_id) REFERENCES client_suppliers(id)
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_supplier_reference_images_client_supplier_id'
      AND object_id = OBJECT_ID('supplier_reference_images')
)
    CREATE INDEX IX_supplier_reference_images_client_supplier_id
        ON supplier_reference_images(client_supplier_id);
GO
