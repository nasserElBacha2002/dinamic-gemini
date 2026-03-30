IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'final_count_records')
BEGIN
    CREATE TABLE final_count_records (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NULL,
        sku NVARCHAR(128) NULL,
        product_name NVARCHAR(512) NULL,
        quantity INT NOT NULL,
        normalized_label_ids_json NVARCHAR(MAX) NOT NULL,
        review_required BIT NOT NULL,
        explanation_summary NVARCHAR(1024) NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL
    );
    CREATE INDEX IX_final_count_scope ON final_count_records(inventory_id, aisle_id);
    CREATE INDEX IX_final_count_position ON final_count_records(position_id);
END;
GO

-- v3.2.3 — Raw labels (original observations)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'raw_labels')
BEGIN
    CREATE TABLE raw_labels (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NULL,
        evidence_id VARCHAR(36) NULL,
        group_key NVARCHAR(256) NOT NULL,
        provider NVARCHAR(64) NOT NULL,
        source_type NVARCHAR(64) NOT NULL,
        source_reference NVARCHAR(256) NULL,
        sku_raw NVARCHAR(128) NULL,
        sku_candidate NVARCHAR(128) NULL,
        product_name_raw NVARCHAR(512) NULL,
        detected_text NVARCHAR(512) NULL,
        confidence FLOAT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL
    );
    CREATE INDEX IX_raw_labels_scope ON raw_labels(inventory_id, aisle_id);
    CREATE INDEX IX_raw_labels_position ON raw_labels(position_id);
    CREATE INDEX IX_raw_labels_group_key ON raw_labels(group_key);
END;
GO

-- v3.2.3 — Normalized labels (post-merge materialization)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'normalized_labels')
BEGIN
    CREATE TABLE normalized_labels (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NULL,
        group_key NVARCHAR(256) NOT NULL,
        canonical_sku NVARCHAR(128) NULL,
        canonical_product_name NVARCHAR(512) NULL,
        raw_label_ids_json NVARCHAR(MAX) NOT NULL,
        merge_rule_applied NVARCHAR(64) NOT NULL,
        merge_confidence FLOAT NULL,
        merge_reason NVARCHAR(512) NOT NULL,
        review_required BIT NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL
    );
    CREATE INDEX IX_normalized_labels_scope ON normalized_labels(inventory_id, aisle_id);
    CREATE INDEX IX_normalized_labels_position ON normalized_labels(position_id);
    CREATE INDEX IX_normalized_labels_group_key ON normalized_labels(group_key);
END;
GO

-- v3.2.4 — Inventory visual references (optional reference images per inventory)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'inventory_visual_references')
BEGIN
    CREATE TABLE inventory_visual_references (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        filename NVARCHAR(512) NOT NULL,
        storage_path NVARCHAR(1024) NOT NULL,
        mime_type VARCHAR(128) NOT NULL,
        file_size BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_inventory_visual_references_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id)
    );
    CREATE INDEX IX_inventory_visual_references_inventory_id ON inventory_visual_references(inventory_id);
END;
GO

-- v3.3.0 — Provider-aware artifact metadata (S3 foundation, additive and backward-compatible)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'storage_provider')
    ALTER TABLE source_assets ADD storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'storage_bucket')
    ALTER TABLE source_assets ADD storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'storage_key')
    ALTER TABLE source_assets ADD storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'content_type')
    ALTER TABLE source_assets ADD content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'file_size_bytes')
    ALTER TABLE source_assets ADD file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'etag')
    ALTER TABLE source_assets ADD etag NVARCHAR(128) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'storage_provider')
    ALTER TABLE inventory_visual_references ADD storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'storage_bucket')
    ALTER TABLE inventory_visual_references ADD storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'storage_key')
    ALTER TABLE inventory_visual_references ADD storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'content_type')
    ALTER TABLE inventory_visual_references ADD content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'file_size_bytes')
    ALTER TABLE inventory_visual_references ADD file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'etag')
    ALTER TABLE inventory_visual_references ADD etag NVARCHAR(128) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'storage_provider')
    ALTER TABLE evidences ADD storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'storage_bucket')
    ALTER TABLE evidences ADD storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'storage_key')
    ALTER TABLE evidences ADD storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'content_type')
    ALTER TABLE evidences ADD content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'file_size_bytes')
    ALTER TABLE evidences ADD file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'etag')
    ALTER TABLE evidences ADD etag NVARCHAR(128) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_storage_provider')
    ALTER TABLE jobs ADD report_storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_storage_bucket')
    ALTER TABLE jobs ADD report_storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_json_storage_key')
    ALTER TABLE jobs ADD report_json_storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_csv_storage_key')
    ALTER TABLE jobs ADD report_csv_storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_content_type')
    ALTER TABLE jobs ADD report_content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_file_size_bytes')
    ALTER TABLE jobs ADD report_file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_etag')
    ALTER TABLE jobs ADD report_etag NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'log_storage_provider')
    ALTER TABLE jobs ADD log_storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'log_storage_bucket')
    ALTER TABLE jobs ADD log_storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_storage_key')
    ALTER TABLE jobs ADD execution_log_storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_content_type')
    ALTER TABLE jobs ADD execution_log_content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_file_size_bytes')
    ALTER TABLE jobs ADD execution_log_file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_etag')
    ALTER TABLE jobs ADD execution_log_etag NVARCHAR(128) NULL;
GO
