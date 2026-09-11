/*
  Version 0105 — canonical physical-position auto-materialization.

  Additive provenance is stored on dbo.aisle_locations. Existing location
  identities and historical codes are not rewritten. The existing filtered
  UQ_aisle_locations_client_aisle_normalized_code_active index remains the
  sole active canonical-identity constraint.
*/

IF COL_LENGTH(N'dbo.aisle_locations', N'creation_source') IS NULL
    ALTER TABLE dbo.aisle_locations ADD creation_source VARCHAR(16) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'recognition_source') IS NULL
    ALTER TABLE dbo.aisle_locations ADD recognition_source VARCHAR(32) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'client_supplier_id') IS NULL
    ALTER TABLE dbo.aisle_locations ADD client_supplier_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'profile_id') IS NULL
    ALTER TABLE dbo.aisle_locations ADD profile_id VARCHAR(36) NULL;
GO
-- Deliberately no profile_id FK: this records an exact extraction-profile snapshot.
-- SQL materialization validates client/supplier/version ownership while permitting
-- inactive or superseded profiles; future profile storage is not constrained here.
IF COL_LENGTH(N'dbo.aisle_locations', N'profile_version') IS NULL
    ALTER TABLE dbo.aisle_locations ADD profile_version INT NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'raw_recognition_code') IS NULL
    ALTER TABLE dbo.aisle_locations ADD raw_recognition_code NVARCHAR(4000) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'pallet') IS NULL
    ALTER TABLE dbo.aisle_locations ADD pallet NVARCHAR(128) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'side') IS NULL
    ALTER TABLE dbo.aisle_locations ADD side NVARCHAR(64) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'level') IS NULL
    ALTER TABLE dbo.aisle_locations ADD level INT NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'marker_index') IS NULL
    ALTER TABLE dbo.aisle_locations ADD marker_index INT NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'marker_total') IS NULL
    ALTER TABLE dbo.aisle_locations ADD marker_total INT NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'source_capture_id') IS NULL
    ALTER TABLE dbo.aisle_locations ADD source_capture_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.aisle_locations', N'auto_materialized_at') IS NULL
    ALTER TABLE dbo.aisle_locations ADD auto_materialized_at DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_created') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_created BIT NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_idempotent_replay') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_idempotent_replay BIT NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_materialization_request_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections
        ADD position_materialization_request_id VARCHAR(36) NULL;
GO

-- Preserve all historical rows as manually created; do not infer recognition provenance.
UPDATE dbo.aisle_locations
SET creation_source = 'MANUAL'
WHERE creation_source IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'DF_aisle_locations_creation_source'
)
    ALTER TABLE dbo.aisle_locations
        ADD CONSTRAINT DF_aisle_locations_creation_source DEFAULT ('MANUAL') FOR creation_source;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'creation_source' AND is_nullable = 1
)
    ALTER TABLE dbo.aisle_locations ALTER COLUMN creation_source VARCHAR(16) NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'CK_aisle_locations_creation_source'
)
    ALTER TABLE dbo.aisle_locations
        ADD CONSTRAINT CK_aisle_locations_creation_source
            CHECK (creation_source IN ('MANUAL', 'AUTO'));
GO

IF OBJECT_ID(N'dbo.client_suppliers', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'FK_aisle_locations_client_supplier'
)
    ALTER TABLE dbo.aisle_locations
        ADD CONSTRAINT FK_aisle_locations_client_supplier
            FOREIGN KEY (client_supplier_id) REFERENCES dbo.client_suppliers(id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'CK_aisle_locations_materialization_hierarchy'
)
    ALTER TABLE dbo.aisle_locations
        ADD CONSTRAINT CK_aisle_locations_materialization_hierarchy CHECK (
            (profile_version IS NULL OR profile_version > 0)
            AND (level IS NULL OR level >= 0)
            AND (marker_index IS NULL OR marker_index > 0)
            AND (marker_total IS NULL OR marker_total > 0)
            AND (
                marker_index IS NULL OR marker_total IS NULL
                OR marker_index <= marker_total
            )
        );
GO

/* Fail closed unless the active canonical identity index has the exact contract. */
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'UQ_aisle_locations_client_aisle_normalized_code_active'
)
AND NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND i.name = N'UQ_aisle_locations_client_aisle_normalized_code_active'
      AND i.is_unique = 1 AND i.is_disabled = 0
      AND i.type_desc = N'NONCLUSTERED' AND i.has_filter = 1
      AND REPLACE(UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
          i.filter_definition, N'[', N''), N']', N''), N'(', N''), N')', N''), N' ', N'')),
          N'=N''ACTIVE''', N'=''ACTIVE''')
          = N'STATUS=''ACTIVE'''
      AND (SELECT COUNT(*) FROM sys.index_columns ic
           WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
             AND ic.key_ordinal > 0) = 3
      AND EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.columns c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
          WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            AND ic.key_ordinal = 1 AND c.name = N'client_id')
      AND EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.columns c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
          WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            AND ic.key_ordinal = 2 AND c.name = N'aisle_id')
      AND EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.columns c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
          WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            AND ic.key_ordinal = 3 AND c.name = N'normalized_code')
)
    THROW 51006, 'Malformed active canonical position identity index', 1;
GO

IF EXISTS (
    SELECT 1 FROM dbo.aisle_locations
    WHERE status = 'ACTIVE'
    GROUP BY client_id, aisle_id, normalized_code
    HAVING COUNT_BIG(*) > 1
)
    THROW 51007, 'Duplicate active canonical position identities detected', 1;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'UQ_aisle_locations_client_aisle_normalized_code_active'
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_locations_client_aisle_normalized_code_active
        ON dbo.aisle_locations(client_id, aisle_id, normalized_code)
        WHERE status = 'ACTIVE';
GO

IF OBJECT_ID(N'dbo.position_materialization_requests', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.position_materialization_requests (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        location_id VARCHAR(36) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        request_hash CHAR(64) NOT NULL,
        normalized_code NVARCHAR(64) NOT NULL,
        source VARCHAR(32) NOT NULL,
        actor VARCHAR(128) NOT NULL,
        result VARCHAR(16) NOT NULL,
        created_at DATETIME2 NOT NULL,
        association_status VARCHAR(24) NOT NULL
            CONSTRAINT DF_pmr_association_status DEFAULT ('PENDING'),
        associated_at DATETIME2 NULL,
        association_error_code VARCHAR(64) NULL,
        CONSTRAINT PK_position_materialization_requests PRIMARY KEY (id),
        CONSTRAINT FK_pmr_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_pmr_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_pmr_aisle FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id),
        CONSTRAINT FK_pmr_location FOREIGN KEY (location_id) REFERENCES dbo.aisle_locations(id),
        CONSTRAINT CK_pmr_result CHECK (result IN ('MATERIALIZED', 'REUSED')),
        CONSTRAINT CK_pmr_request_hash CHECK (LEN(request_hash) = 64),
        CONSTRAINT CK_pmr_association_state CHECK (
            (association_status = 'PENDING'
                AND associated_at IS NULL AND association_error_code IS NULL)
            OR (association_status = 'ASSOCIATED'
                AND associated_at IS NOT NULL AND association_error_code IS NULL)
            OR (association_status = 'REQUIRES_REVIEW'
                AND associated_at IS NULL AND association_error_code IS NOT NULL)
        )
    );
END
GO

IF COL_LENGTH(N'dbo.position_materialization_requests', N'association_status') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD association_status VARCHAR(24) NULL;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'associated_at') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD associated_at DATETIME2 NULL;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'association_error_code') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD association_error_code VARCHAR(64) NULL;
GO

UPDATE dbo.position_materialization_requests
SET association_status = 'PENDING'
WHERE association_status IS NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'DF_pmr_association_status'
)
    ALTER TABLE dbo.position_materialization_requests
        ADD CONSTRAINT DF_pmr_association_status DEFAULT ('PENDING') FOR association_status;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'association_status' AND is_nullable = 1
)
    ALTER TABLE dbo.position_materialization_requests
        ALTER COLUMN association_status VARCHAR(24) NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_association_state'
)
    ALTER TABLE dbo.position_materialization_requests
        ADD CONSTRAINT CK_pmr_association_state CHECK (
            (association_status = 'PENDING'
                AND associated_at IS NULL AND association_error_code IS NULL)
            OR (association_status = 'ASSOCIATED'
                AND associated_at IS NOT NULL AND association_error_code IS NULL)
            OR (association_status = 'REQUIRES_REVIEW'
                AND associated_at IS NULL AND association_error_code IS NOT NULL)
        );
GO

/*
  Preflight duplicate diagnostic before adding ledger uniqueness. This returns
  the conflicting tenant/key pairs for operator inspection on a partial schema.
*/
SELECT client_id, idempotency_key, COUNT_BIG(*) AS duplicate_count
FROM dbo.position_materialization_requests
GROUP BY client_id, idempotency_key
HAVING COUNT_BIG(*) > 1;
GO

IF EXISTS (
    SELECT 1
    FROM dbo.position_materialization_requests
    GROUP BY client_id, idempotency_key
    HAVING COUNT_BIG(*) > 1
)
    THROW 51005, 'Duplicate position materialization idempotency keys detected', 1;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'UQ_pmr_client_idempotency_key'
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_pmr_client_idempotency_key
        ON dbo.position_materialization_requests(client_id, idempotency_key);
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND i.name = N'UQ_pmr_client_idempotency_key'
      AND i.is_unique = 1 AND i.is_disabled = 0
      AND i.type_desc = N'NONCLUSTERED' AND i.has_filter = 0
      AND (SELECT COUNT(*) FROM sys.index_columns ic
           WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
             AND ic.key_ordinal > 0) = 2
      AND EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.columns c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
          WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            AND ic.key_ordinal = 1 AND c.name = N'client_id')
      AND EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.columns c
          ON c.object_id = ic.object_id AND c.column_id = ic.column_id
          WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            AND ic.key_ordinal = 2 AND c.name = N'idempotency_key')
)
    THROW 51008, 'Malformed position materialization ledger unique index', 1;
GO

-- Non-unique lookup indexes contain no additional identity contract.
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'IX_pmr_location_created_at'
)
    CREATE NONCLUSTERED INDEX IX_pmr_location_created_at
        ON dbo.position_materialization_requests(location_id, created_at);
GO
