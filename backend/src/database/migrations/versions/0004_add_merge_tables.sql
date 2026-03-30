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

