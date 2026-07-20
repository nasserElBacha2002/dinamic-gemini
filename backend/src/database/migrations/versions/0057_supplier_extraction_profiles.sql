-- Phase 6 — Supplier extraction profiles + reference annotations.
-- Additive + idempotent. Keep aligned with backend/src/database/schema.sql.

IF OBJECT_ID('supplier_extraction_profiles', 'U') IS NULL
BEGIN
    CREATE TABLE supplier_extraction_profiles (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        supplier_id VARCHAR(36) NOT NULL,
        profile_key VARCHAR(128) NOT NULL,
        version INT NOT NULL,
        status VARCHAR(32) NOT NULL,
        configuration_json NVARCHAR(MAX) NOT NULL,
        visual_notes NVARCHAR(MAX) NULL,
        created_by VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        activated_by VARCHAR(128) NULL,
        activated_at DATETIME2 NULL,
        superseded_at DATETIME2 NULL,
        updated_at DATETIME2 NOT NULL,
        row_version INT NOT NULL CONSTRAINT DF_sep_row_version DEFAULT (1),
        CONSTRAINT PK_supplier_extraction_profiles PRIMARY KEY (id),
        CONSTRAINT CK_sep_status CHECK (
            status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'SUPERSEDED')
        ),
        CONSTRAINT CK_sep_version CHECK (version > 0),
        CONSTRAINT FK_sep_client FOREIGN KEY (client_id) REFERENCES clients(id),
        CONSTRAINT FK_sep_supplier FOREIGN KEY (supplier_id) REFERENCES client_suppliers(id)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_sep_client_supplier_version'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_sep_client_supplier_version
        ON supplier_extraction_profiles(client_id, supplier_id, version);
GO

-- SQL Server filtered unique index: at most one ACTIVE profile per client+supplier.
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_sep_one_active'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_sep_one_active
        ON supplier_extraction_profiles(client_id, supplier_id)
        WHERE status = 'ACTIVE';
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_sep_supplier_status'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE NONCLUSTERED INDEX IX_sep_supplier_status
        ON supplier_extraction_profiles(supplier_id, status, version DESC);
GO

IF OBJECT_ID('supplier_reference_annotations', 'U') IS NULL
BEGIN
    CREATE TABLE supplier_reference_annotations (
        id VARCHAR(36) NOT NULL,
        template_image_id VARCHAR(36) NOT NULL,
        profile_id VARCHAR(36) NULL,
        field_key VARCHAR(64) NOT NULL,
        anchor_texts_json NVARCHAR(MAX) NOT NULL,
        spatial_relation VARCHAR(32) NOT NULL,
        normalized_polygon_json NVARCHAR(MAX) NULL,
        priority INT NOT NULL CONSTRAINT DF_sra_priority DEFAULT (1),
        required BIT NOT NULL CONSTRAINT DF_sra_required DEFAULT (0),
        max_distance_ratio FLOAT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_supplier_reference_annotations PRIMARY KEY (id),
        CONSTRAINT CK_sra_spatial CHECK (
            spatial_relation IN (
                'RIGHT_OF', 'LEFT_OF', 'ABOVE', 'BELOW',
                'SAME_ROW', 'SAME_COLUMN', 'SAME_CELL',
                'NEAR', 'INSIDE_REGION'
            )
        ),
        CONSTRAINT FK_sra_template FOREIGN KEY (template_image_id)
            REFERENCES supplier_reference_images(id),
        CONSTRAINT FK_sra_profile FOREIGN KEY (profile_id)
            REFERENCES supplier_extraction_profiles(id)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_sra_template'
      AND object_id = OBJECT_ID('supplier_reference_annotations')
)
    CREATE NONCLUSTERED INDEX IX_sra_template
        ON supplier_reference_annotations(template_image_id, priority);
GO

-- Optional template family metadata on existing reference images (additive).
IF COL_LENGTH('supplier_reference_images', 'template_family') IS NULL
    ALTER TABLE supplier_reference_images ADD template_family VARCHAR(128) NULL;
GO

IF COL_LENGTH('supplier_reference_images', 'orientation_hint') IS NULL
    ALTER TABLE supplier_reference_images ADD orientation_hint VARCHAR(64) NULL;
GO

IF COL_LENGTH('supplier_reference_images', 'document_type') IS NULL
    ALTER TABLE supplier_reference_images ADD document_type VARCHAR(64) NULL;
GO

IF COL_LENGTH('supplier_reference_images', 'profile_version') IS NULL
    ALTER TABLE supplier_reference_images ADD profile_version INT NULL;
GO
