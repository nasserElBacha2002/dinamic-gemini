/*
  0088_product_label_identity.sql

  Physical product labels (D1 format):
  - issued_product_labels: mint/print registry (global unique label_id, never recycle)
  - inventory_counted_product_labels: inventory-scoped counting uniqueness
  - product_records.label_id: optional FK-ish identity on counted rows

  Rollback: 0088_product_label_identity.down.sql
*/

-- ---------------------------------------------------------------------------
-- issued_product_labels (print / mint)
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.issued_product_labels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.issued_product_labels (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        label_id VARCHAR(16) NOT NULL,
        internal_code NVARCHAR(48) NOT NULL,
        quantity INT NOT NULL,
        format_version VARCHAR(8) NOT NULL
            CONSTRAINT DF_issued_product_labels_format DEFAULT ('D1'),
        checksum CHAR(1) NOT NULL,
        payload NVARCHAR(160) NOT NULL,
        created_at DATETIME2 NOT NULL,
        created_by VARCHAR(128) NULL,
        CONSTRAINT PK_issued_product_labels PRIMARY KEY (id),
        CONSTRAINT FK_issued_product_labels_client
            FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT CK_issued_product_labels_quantity CHECK (quantity >= 1)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_issued_product_labels_label_id'
      AND object_id = OBJECT_ID(N'dbo.issued_product_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_issued_product_labels_label_id
        ON dbo.issued_product_labels(label_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_issued_product_labels_client'
      AND object_id = OBJECT_ID(N'dbo.issued_product_labels')
)
    CREATE NONCLUSTERED INDEX IX_issued_product_labels_client
        ON dbo.issued_product_labels(client_id, created_at DESC);
GO

-- ---------------------------------------------------------------------------
-- inventory_counted_product_labels (dedupe across photos within inventory)
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.inventory_counted_product_labels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.inventory_counted_product_labels (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        label_id VARCHAR(16) NOT NULL,
        first_product_record_id VARCHAR(36) NOT NULL,
        first_source_asset_id VARCHAR(36) NOT NULL,
        first_job_id VARCHAR(36) NOT NULL,
        first_position_id VARCHAR(36) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_inventory_counted_product_labels PRIMARY KEY (id),
        CONSTRAINT FK_icpl_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_icpl_inventory_label
        ON dbo.inventory_counted_product_labels(inventory_id, label_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_icpl_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
    CREATE NONCLUSTERED INDEX IX_icpl_label
        ON dbo.inventory_counted_product_labels(label_id);
GO

-- ---------------------------------------------------------------------------
-- product_records.label_id (nullable for legacy)
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.product_records') AND name = N'label_id'
)
    ALTER TABLE dbo.product_records ADD label_id VARCHAR(16) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_product_records_label_id'
      AND object_id = OBJECT_ID(N'dbo.product_records')
)
    CREATE NONCLUSTERED INDEX IX_product_records_label_id
        ON dbo.product_records(label_id)
        WHERE label_id IS NOT NULL;
GO
