-- Phase 1 — Label recognition profile source selection (ITEM/POSITION) per ClientSupplier.
-- Additive: no runtime behavior change; legacy supplier configs default label_kind to ITEM.

IF OBJECT_ID('client_supplier_label_profiles', 'U') IS NULL
BEGIN
    CREATE TABLE client_supplier_label_profiles (
        id VARCHAR(36) NOT NULL,
        client_supplier_id VARCHAR(36) NOT NULL,
        label_kind VARCHAR(16) NOT NULL,
        source VARCHAR(16) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_client_supplier_label_profiles PRIMARY KEY (id),
        CONSTRAINT FK_cslp_client_supplier
            FOREIGN KEY (client_supplier_id) REFERENCES client_suppliers(id),
        CONSTRAINT CK_cslp_label_kind CHECK (label_kind IN ('ITEM', 'POSITION')),
        CONSTRAINT CK_cslp_source CHECK (source IN ('DINAMIC', 'SUPPLIER')),
        CONSTRAINT UQ_cslp_supplier_kind UNIQUE (client_supplier_id, label_kind)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_cslp_client_supplier_id'
      AND object_id = OBJECT_ID('client_supplier_label_profiles')
)
BEGIN
    CREATE INDEX IX_cslp_client_supplier_id
        ON client_supplier_label_profiles(client_supplier_id);
END;
GO

IF COL_LENGTH('aisles', 'item_profile_source_override') IS NULL
    ALTER TABLE aisles ADD item_profile_source_override VARCHAR(16) NULL;
GO

IF COL_LENGTH('aisles', 'position_profile_source_override') IS NULL
    ALTER TABLE aisles ADD position_profile_source_override VARCHAR(16) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_aisles_item_profile_source_override'
      AND parent_object_id = OBJECT_ID('aisles')
)
BEGIN
    ALTER TABLE aisles
    ADD CONSTRAINT CK_aisles_item_profile_source_override
        CHECK (
            item_profile_source_override IS NULL
            OR item_profile_source_override IN ('DINAMIC', 'SUPPLIER')
        );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_aisles_position_profile_source_override'
      AND parent_object_id = OBJECT_ID('aisles')
)
BEGIN
    ALTER TABLE aisles
    ADD CONSTRAINT CK_aisles_position_profile_source_override
        CHECK (
            position_profile_source_override IS NULL
            OR position_profile_source_override IN ('DINAMIC', 'SUPPLIER')
        );
END;
GO

IF COL_LENGTH('supplier_extraction_profiles', 'label_kind') IS NULL
    ALTER TABLE supplier_extraction_profiles ADD label_kind VARCHAR(16) NULL;
GO

IF COL_LENGTH('supplier_prompt_configs', 'label_kind') IS NULL
    ALTER TABLE supplier_prompt_configs ADD label_kind VARCHAR(16) NULL;
GO

IF COL_LENGTH('supplier_reference_images', 'label_kind') IS NULL
    ALTER TABLE supplier_reference_images ADD label_kind VARCHAR(16) NULL;
GO

-- Legacy configs were product/item oriented; safe default documented in Phase 1 audit.
UPDATE supplier_extraction_profiles
SET label_kind = 'ITEM'
WHERE label_kind IS NULL;
GO

UPDATE supplier_prompt_configs
SET label_kind = 'ITEM'
WHERE label_kind IS NULL;
GO

UPDATE supplier_reference_images
SET label_kind = 'ITEM'
WHERE label_kind IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_sep_label_kind'
      AND parent_object_id = OBJECT_ID('supplier_extraction_profiles')
)
BEGIN
    ALTER TABLE supplier_extraction_profiles
    ADD CONSTRAINT CK_sep_label_kind
        CHECK (label_kind IS NULL OR label_kind IN ('ITEM', 'POSITION'));
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_spc_label_kind'
      AND parent_object_id = OBJECT_ID('supplier_prompt_configs')
)
BEGIN
    ALTER TABLE supplier_prompt_configs
    ADD CONSTRAINT CK_spc_label_kind
        CHECK (label_kind IS NULL OR label_kind IN ('ITEM', 'POSITION'));
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_sri_label_kind'
      AND parent_object_id = OBJECT_ID('supplier_reference_images')
)
BEGIN
    ALTER TABLE supplier_reference_images
    ADD CONSTRAINT CK_sri_label_kind
        CHECK (label_kind IS NULL OR label_kind IN ('ITEM', 'POSITION'));
END;
GO
