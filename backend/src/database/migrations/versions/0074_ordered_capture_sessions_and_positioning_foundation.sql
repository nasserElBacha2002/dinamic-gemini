/*
  0074_ordered_capture_sessions_and_positioning_foundation.sql

  Phase 1 — logical capture order, sealed sessions, aisle locations + positioning labels.

  Naming note:
  - Domain CV "positions" (detected products) stay in dbo.positions.
  - Physical shelf/rack locations use dbo.aisle_locations.
  - Emitted positioning labels use dbo.aisle_location_labels.
  - Ordered mobile capture sessions use dbo.ordered_capture_sessions
    (distinct from web ingestion dbo.capture_sessions).

  Rollback notes (manual):
  - Prefer executable script:
    0074_ordered_capture_sessions_and_positioning_foundation.down.sql
  - DROP indexes/constraints introduced below (filtered unique indexes first).
  - DROP TABLE aisle_location_labels, aisle_locations, ordered_capture_sessions.
  - ALTER TABLE source_assets / inventory_jobs / job_source_assets DROP new columns.
  - Do not drop legacy data; new columns are nullable for legacy rows.
  - Corrections live in 0075_phase1_positioning_corrections.sql (+ matching .down.sql).
*/

-- ---------------------------------------------------------------------------
-- 1) Ordered capture sessions (mobile → process spine)
-- ---------------------------------------------------------------------------
IF OBJECT_ID('dbo.ordered_capture_sessions', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ordered_capture_sessions (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        expected_asset_count INT NULL,
        uploaded_asset_count INT NOT NULL
            CONSTRAINT DF_ordered_capture_sessions_uploaded DEFAULT (0),
        sequence_version INT NOT NULL
            CONSTRAINT DF_ordered_capture_sessions_seq_ver DEFAULT (1),
        created_by VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        sealed_at DATETIME2 NULL,
        processing_started_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        CONSTRAINT PK_ordered_capture_sessions PRIMARY KEY (id),
        CONSTRAINT FK_ordered_capture_sessions_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_ordered_capture_sessions_aisle
            FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id),
        CONSTRAINT CK_ordered_capture_sessions_status CHECK (
            status IN ('OPEN', 'UPLOADING', 'SEALED', 'PROCESSING', 'COMPLETED', 'FAILED')
        ),
        CONSTRAINT CK_ordered_capture_sessions_counts CHECK (
            uploaded_asset_count >= 0
            AND (expected_asset_count IS NULL OR expected_asset_count >= 0)
            AND sequence_version >= 1
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ordered_capture_sessions_aisle_status'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    CREATE NONCLUSTERED INDEX IX_ordered_capture_sessions_aisle_status
        ON dbo.ordered_capture_sessions(aisle_id, status, updated_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ordered_capture_sessions_inventory'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    CREATE NONCLUSTERED INDEX IX_ordered_capture_sessions_inventory
        ON dbo.ordered_capture_sessions(inventory_id, created_at DESC);
GO

-- ---------------------------------------------------------------------------
-- 2) source_assets: logical sequence (nullable for legacy)
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'ordered_capture_session_id'
)
    ALTER TABLE dbo.source_assets ADD ordered_capture_session_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'sequence_number'
)
    ALTER TABLE dbo.source_assets ADD sequence_number INT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'sequence_source'
)
    ALTER TABLE dbo.source_assets ADD sequence_source VARCHAR(32) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_source_assets_ordered_capture_session'
)
BEGIN
    ALTER TABLE dbo.source_assets
        ADD CONSTRAINT FK_source_assets_ordered_capture_session
        FOREIGN KEY (ordered_capture_session_id)
        REFERENCES dbo.ordered_capture_sessions(id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_source_assets_sequence_source'
)
    ALTER TABLE dbo.source_assets
        ADD CONSTRAINT CK_source_assets_sequence_source CHECK (
            sequence_source IS NULL
            OR sequence_source IN ('CLIENT_ASSIGNED', 'LEGACY_DERIVED')
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_source_assets_sequence_number_positive'
)
    ALTER TABLE dbo.source_assets
        ADD CONSTRAINT CK_source_assets_sequence_number_positive CHECK (
            sequence_number IS NULL OR sequence_number >= 1
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_source_assets_ordered_session_sequence'
      AND object_id = OBJECT_ID(N'dbo.source_assets')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_source_assets_ordered_session_sequence
        ON dbo.source_assets(ordered_capture_session_id, sequence_number)
        WHERE ordered_capture_session_id IS NOT NULL AND sequence_number IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_source_assets_ordered_session_client_file'
      AND object_id = OBJECT_ID(N'dbo.source_assets')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_source_assets_ordered_session_client_file
        ON dbo.source_assets(ordered_capture_session_id, upload_client_file_id)
        WHERE ordered_capture_session_id IS NOT NULL AND upload_client_file_id IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_source_assets_ordered_session_sequence'
      AND object_id = OBJECT_ID(N'dbo.source_assets')
)
    CREATE NONCLUSTERED INDEX IX_source_assets_ordered_session_sequence
        ON dbo.source_assets(ordered_capture_session_id, sequence_number)
        WHERE ordered_capture_session_id IS NOT NULL;
GO

-- ---------------------------------------------------------------------------
-- 3) inventory_jobs: pin sealed session + version
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_jobs') AND name = N'ordered_capture_session_id'
)
    ALTER TABLE dbo.inventory_jobs ADD ordered_capture_session_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_jobs') AND name = N'sequence_version'
)
    ALTER TABLE dbo.inventory_jobs ADD sequence_version INT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_inventory_jobs_ordered_capture_session'
)
BEGIN
    ALTER TABLE dbo.inventory_jobs
        ADD CONSTRAINT FK_inventory_jobs_ordered_capture_session
        FOREIGN KEY (ordered_capture_session_id)
        REFERENCES dbo.ordered_capture_sessions(id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_inventory_jobs_ordered_session_version'
      AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_inventory_jobs_ordered_session_version
        ON dbo.inventory_jobs(ordered_capture_session_id, sequence_version)
        WHERE ordered_capture_session_id IS NOT NULL AND sequence_version IS NOT NULL;
GO

-- ---------------------------------------------------------------------------
-- 4) job_source_assets: preserve client sequence (alias of position_order when set)
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.job_source_assets') AND name = N'sequence_number'
)
    ALTER TABLE dbo.job_source_assets ADD sequence_number INT NULL;
GO

-- ---------------------------------------------------------------------------
-- 5) Aisle locations (physical positioning — NOT CV positions)
-- ---------------------------------------------------------------------------
IF OBJECT_ID('dbo.aisle_locations', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.aisle_locations (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        code NVARCHAR(128) NOT NULL,
        normalized_code NVARCHAR(128) NOT NULL,
        display_name NVARCHAR(256) NULL,
        description NVARCHAR(1024) NULL,
        status VARCHAR(32) NOT NULL,
        created_by VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aisle_locations PRIMARY KEY (id),
        CONSTRAINT FK_aisle_locations_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_aisle_locations_aisle FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id),
        CONSTRAINT CK_aisle_locations_status CHECK (status IN ('ACTIVE', 'INACTIVE'))
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_locations_client_aisle_normalized_code_active'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_locations_client_aisle_normalized_code_active
        ON dbo.aisle_locations(client_id, aisle_id, normalized_code)
        WHERE status = 'ACTIVE';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_locations_aisle_status'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    CREATE NONCLUSTERED INDEX IX_aisle_locations_aisle_status
        ON dbo.aisle_locations(aisle_id, status, normalized_code);
GO

-- ---------------------------------------------------------------------------
-- 6) Positioning labels (logical emission; render deferred)
-- ---------------------------------------------------------------------------
IF OBJECT_ID('dbo.aisle_location_labels', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.aisle_location_labels (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        location_id VARCHAR(36) NOT NULL,
        public_identifier VARCHAR(64) NOT NULL,
        payload_version INT NOT NULL
            CONSTRAINT DF_aisle_location_labels_payload_ver DEFAULT (1),
        marker_version INT NOT NULL
            CONSTRAINT DF_aisle_location_labels_marker_ver DEFAULT (1),
        template_version INT NOT NULL
            CONSTRAINT DF_aisle_location_labels_template_ver DEFAULT (1),
        status VARCHAR(32) NOT NULL,
        payload_json NVARCHAR(MAX) NOT NULL,
        payload_hash VARCHAR(128) NULL,
        signature_status VARCHAR(32) NOT NULL
            CONSTRAINT DF_aisle_location_labels_sig DEFAULT ('NOT_IMPLEMENTED'),
        generated_by VARCHAR(128) NULL,
        generated_at DATETIME2 NOT NULL,
        invalidated_at DATETIME2 NULL,
        invalidation_reason NVARCHAR(512) NULL,
        replaced_by_label_id VARCHAR(36) NULL,
        CONSTRAINT PK_aisle_location_labels PRIMARY KEY (id),
        CONSTRAINT FK_aisle_location_labels_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_aisle_location_labels_location FOREIGN KEY (location_id) REFERENCES dbo.aisle_locations(id),
        CONSTRAINT CK_aisle_location_labels_status CHECK (
            status IN ('ACTIVE', 'REPLACED', 'INVALIDATED', 'ARCHIVED')
        ),
        CONSTRAINT CK_aisle_location_labels_signature_status CHECK (
            signature_status IN ('NOT_IMPLEMENTED', 'UNSIGNED', 'SIGNED')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_labels_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_location_labels_public_identifier
        ON dbo.aisle_location_labels(public_identifier);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_location_labels_location_status'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    CREATE NONCLUSTERED INDEX IX_aisle_location_labels_location_status
        ON dbo.aisle_location_labels(location_id, status, generated_at DESC);
GO
