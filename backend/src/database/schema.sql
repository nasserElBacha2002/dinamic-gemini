-- Stage 8 — SQL Server schema for jobs, pallet_results, job_events.
-- Database: dinamic-gemini

-- Jobs: lifecycle, config, outputs (no binaries)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'jobs')
BEGIN
    CREATE TABLE jobs (
        id VARCHAR(64) NOT NULL PRIMARY KEY,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        status VARCHAR(16) NOT NULL,
        mode VARCHAR(16) NOT NULL,
        confidence_threshold FLOAT NOT NULL,
        video_filename VARCHAR(255) NULL,
        video_path NVARCHAR(1024) NULL,
        frames_count_sent INT NULL,
        gemini_calls INT NULL,
        progress_stage VARCHAR(64) NULL,
        progress_percent INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        artifacts_dir NVARCHAR(1024) NULL,
        report_json_path NVARCHAR(1024) NULL,
        report_csv_path NVARCHAR(1024) NULL,
        report_storage_provider VARCHAR(16) NULL,
        report_storage_bucket NVARCHAR(255) NULL,
        report_json_storage_key NVARCHAR(1024) NULL,
        report_csv_storage_key NVARCHAR(1024) NULL,
        report_content_type VARCHAR(128) NULL,
        report_file_size_bytes BIGINT NULL,
        report_etag NVARCHAR(128) NULL,
        log_storage_provider VARCHAR(16) NULL,
        log_storage_bucket NVARCHAR(255) NULL,
        execution_log_storage_key NVARCHAR(1024) NULL,
        execution_log_content_type VARCHAR(128) NULL,
        execution_log_file_size_bytes BIGINT NULL,
        execution_log_etag NVARCHAR(128) NULL,
        engine_version VARCHAR(32) NOT NULL,
        prompt_version VARCHAR(64) NULL,
        metadata NVARCHAR(MAX) NULL
    );
END;
GO

-- Stage 2.2.A — Photos input (optional columns; add if missing)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'input_type')
    ALTER TABLE jobs ADD input_type VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'input_manifest_path')
    ALTER TABLE jobs ADD input_manifest_path NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'photos_dir')
    ALTER TABLE jobs ADD photos_dir NVARCHAR(1024) NULL;
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

-- Pallet results per job (one row per pallet)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'pallet_results')
BEGIN
    CREATE TABLE pallet_results (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        job_id VARCHAR(64) NOT NULL,
        pallet_id VARCHAR(32) NOT NULL,
        internal_code VARCHAR(64) NULL,
        quantity INT NULL,
        source VARCHAR(32) NOT NULL,
        confidence FLOAT NULL,
        fallback_used BIT NOT NULL DEFAULT 0,
        raw_estimated_visible_boxes INT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_pallet_results_job FOREIGN KEY (job_id) REFERENCES jobs(id)
    );
    CREATE INDEX IX_pallet_results_job_id ON pallet_results(job_id);
END;
GO

-- Epic 3.1.B — Traceability (source_image_id, traceability_status)
-- Each row = one pipeline entity (one counted result). source_image_id = single source image for that entity.
-- Allowed traceability_status values: valid, missing, invalid, unvalidated (application-enforced; no CHECK to keep migrations safe).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('pallet_results') AND name = 'source_image_id')
    ALTER TABLE pallet_results ADD source_image_id NVARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('pallet_results') AND name = 'traceability_status')
    ALTER TABLE pallet_results ADD traceability_status NVARCHAR(32) NULL;
GO

-- Job events (audit timeline)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_events')
BEGIN
    CREATE TABLE job_events (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        job_id VARCHAR(64) NOT NULL,
        [timestamp] DATETIME2 NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        payload NVARCHAR(MAX) NULL,
        CONSTRAINT FK_job_events_job FOREIGN KEY (job_id) REFERENCES jobs(id)
    );
    CREATE INDEX IX_job_events_job_id_timestamp ON job_events(job_id, [timestamp]);
END;
GO

-- v3.0 — Inventories (Épica 2, Documento técnico §7.1)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'inventories')
BEGIN
    CREATE TABLE inventories (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        name NVARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        completed_at DATETIME2 NULL
    );
END;
GO

-- v3 processing mode + operational primary snapshot (see migrations/versions/0013_inventory_processing_mode.sql)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'processing_mode')
    ALTER TABLE inventories ADD processing_mode VARCHAR(20) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_provider_name')
    ALTER TABLE inventories ADD primary_provider_name NVARCHAR(100) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_model_name')
    ALTER TABLE inventories ADD primary_model_name NVARCHAR(150) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_prompt_key')
    ALTER TABLE inventories ADD primary_prompt_key NVARCHAR(150) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_prompt_version')
    ALTER TABLE inventories ADD primary_prompt_version NVARCHAR(50) NULL;
GO

-- Align processing_mode with migrations/versions/0013_inventory_processing_mode.sql (backfill, NOT NULL, default).
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'processing_mode')
BEGIN
    UPDATE inventories SET processing_mode = 'test' WHERE processing_mode IS NULL;
END;
GO
IF EXISTS (
    SELECT * FROM sys.columns c
    WHERE c.object_id = OBJECT_ID('inventories') AND c.name = 'processing_mode' AND c.is_nullable = 1
)
    ALTER TABLE inventories ALTER COLUMN processing_mode VARCHAR(20) NOT NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('inventories') AND name = 'DF_inventories_processing_mode'
)
    ALTER TABLE inventories ADD CONSTRAINT DF_inventories_processing_mode DEFAULT ('production') FOR processing_mode;
GO
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'client_id')
    ALTER TABLE inventories ADD client_id VARCHAR(36) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys WHERE name = 'FK_inventories_client'
)
BEGIN
    ALTER TABLE inventories
    ADD CONSTRAINT FK_inventories_client
    FOREIGN KEY (client_id) REFERENCES clients(id);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'IX_inventories_client_id' AND object_id = OBJECT_ID('inventories')
)
    CREATE INDEX IX_inventories_client_id ON inventories(client_id);
GO

-- Phase A1 — Clients foundation (mirror migrations/versions/0024_clients_foundation.sql).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'clients')
BEGIN
    CREATE TABLE clients (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        name NVARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL
    );
    CREATE INDEX IX_clients_created_at ON clients(created_at DESC);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('clients') AND name = 'DF_clients_status'
)
    ALTER TABLE clients ADD CONSTRAINT DF_clients_status DEFAULT ('active') FOR status;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_clients_name' AND object_id = OBJECT_ID('clients'))
    CREATE INDEX IX_clients_name ON clients(name);
GO

-- Phase A2 — Client suppliers foundation (mirror migrations/versions/0025_client_suppliers_foundation.sql).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'client_suppliers')
BEGIN
    CREATE TABLE client_suppliers (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        client_id VARCHAR(36) NOT NULL,
        name NVARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_client_suppliers_client FOREIGN KEY (client_id) REFERENCES clients(id),
        CONSTRAINT UQ_client_suppliers_client_name UNIQUE (client_id, name)
    );
    CREATE INDEX IX_client_suppliers_client_id ON client_suppliers(client_id);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('client_suppliers') AND name = 'DF_client_suppliers_status'
)
    ALTER TABLE client_suppliers ADD CONSTRAINT DF_client_suppliers_status DEFAULT ('active') FOR status;
GO

-- v3.0 — Aisles (Épica 2, Documento técnico §7.2; FK for future AisleRepository)
-- Domain assumption: one code per inventory (UNIQUE inventory_id, code).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'aisles')
BEGIN
    CREATE TABLE aisles (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        code VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(512) NULL,
        retryable BIT NULL,
        is_active BIT NOT NULL DEFAULT 1,
        CONSTRAINT FK_aisles_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT UQ_aisles_inventory_code UNIQUE (inventory_id, code)
    );
        CREATE INDEX IX_aisles_inventory_id ON aisles(inventory_id);
END;
GO

-- v3.0 — Inventory jobs (Épica 4; domain Job entity for process_aisle). Normalized from v3_jobs (Stage 4).
--
-- SUPPORTED STATES (script is idempotent for these):
--   1. Fresh install: neither v3_jobs nor inventory_jobs → creates inventory_jobs with IX_inventory_jobs_target.
--   2. Pre-migration: v3_jobs exists, inventory_jobs does not → renames table then index (with guard).
--   3. Already migrated: inventory_jobs exists → no action (outer IF skips block).
-- UNSUPPORTED / OPERATOR INTERVENTION: Both v3_jobs and inventory_jobs exist (e.g. manual partial run).
--   Script does not touch tables; application uses inventory_jobs. Operator may drop or archive v3_jobs if desired.
--
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'inventory_jobs')
BEGIN
    IF EXISTS (SELECT * FROM sys.tables WHERE name = 'v3_jobs')
    BEGIN
        -- Migration: rename v3_jobs to inventory_jobs (data-preserving).
        EXEC sp_rename 'dbo.v3_jobs', 'inventory_jobs';
        -- Rename index only if it still has the old name (idempotent if index was already renamed manually).
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.inventory_jobs') AND name = 'IX_v3_jobs_target')
            EXEC sp_rename 'dbo.inventory_jobs.IX_v3_jobs_target', 'IX_inventory_jobs_target', 'INDEX';
    END
    ELSE
    BEGIN
        -- New install: create inventory_jobs directly.
        CREATE TABLE inventory_jobs (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            target_type VARCHAR(32) NOT NULL,
            target_id VARCHAR(36) NOT NULL,
            job_type VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL,
            payload_json NVARCHAR(MAX) NULL,
            result_json NVARCHAR(MAX) NULL,
            error_message NVARCHAR(2048) NULL,
            created_at DATETIME2 NOT NULL,
            updated_at DATETIME2 NOT NULL,
            started_at DATETIME2 NULL,
            finished_at DATETIME2 NULL,
            last_heartbeat_at DATETIME2 NULL,
            cancel_requested_at DATETIME2 NULL,
            current_stage NVARCHAR(128) NULL,
            current_substep NVARCHAR(128) NULL,
            current_step_started_at DATETIME2 NULL,
            attempt_count INT NOT NULL DEFAULT 1,
            retry_of_job_id VARCHAR(36) NULL,
            failure_code VARCHAR(64) NULL,
            failure_message NVARCHAR(2048) NULL,
            execution_id VARCHAR(64) NULL
        );
        CREATE INDEX IX_inventory_jobs_target ON inventory_jobs(target_type, target_id);
    END
END;
GO
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'started_at')
    ALTER TABLE inventory_jobs ADD started_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finished_at')
    ALTER TABLE inventory_jobs ADD finished_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'last_heartbeat_at')
    ALTER TABLE inventory_jobs ADD last_heartbeat_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'cancel_requested_at')
    ALTER TABLE inventory_jobs ADD cancel_requested_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_stage')
    ALTER TABLE inventory_jobs ADD current_stage NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_substep')
    ALTER TABLE inventory_jobs ADD current_substep NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_step_started_at')
    ALTER TABLE inventory_jobs ADD current_step_started_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'attempt_count')
    ALTER TABLE inventory_jobs ADD attempt_count INT NOT NULL DEFAULT 1;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'retry_of_job_id')
    ALTER TABLE inventory_jobs ADD retry_of_job_id VARCHAR(36) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'failure_code')
    ALTER TABLE inventory_jobs ADD failure_code VARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'failure_message')
    ALTER TABLE inventory_jobs ADD failure_message NVARCHAR(2048) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'execution_id')
    ALTER TABLE inventory_jobs ADD execution_id VARCHAR(64) NULL;
-- Phase 1 multi-run (mirror migrations/versions/0010_multi_run_job_scoping.sql; update both when changing).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'provider_name')
    ALTER TABLE inventory_jobs ADD provider_name NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'model_name')
    ALTER TABLE inventory_jobs ADD model_name NVARCHAR(256) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'prompt_key')
    ALTER TABLE inventory_jobs ADD prompt_key NVARCHAR(256) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'engine_params_json')
    ALTER TABLE inventory_jobs ADD engine_params_json NVARCHAR(MAX) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'prompt_version')
    ALTER TABLE inventory_jobs ADD prompt_version NVARCHAR(256) NULL;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_inventory_jobs_provider_model_prompt' AND object_id = OBJECT_ID('inventory_jobs'))
    CREATE INDEX IX_inventory_jobs_provider_model_prompt ON inventory_jobs(provider_name, model_name, prompt_key);
GO

-- Phase 2 — aisles.operational_job_id (mirror migrations/versions/0011_aisle_operational_job.sql).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'operational_job_id')
BEGIN
    ALTER TABLE aisles ADD operational_job_id VARCHAR(36) NULL;
    ALTER TABLE aisles ADD CONSTRAINT FK_aisles_operational_job FOREIGN KEY (operational_job_id) REFERENCES inventory_jobs(id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_aisles_operational_job_id' AND object_id = OBJECT_ID('aisles'))
    CREATE INDEX IX_aisles_operational_job_id ON aisles(operational_job_id);
GO

-- Phase A4 — aisles.client_supplier_id (nullable foundation only).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'client_supplier_id')
    ALTER TABLE aisles ADD client_supplier_id VARCHAR(36) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys WHERE name = 'FK_aisles_client_supplier'
)
BEGIN
    ALTER TABLE aisles
    ADD CONSTRAINT FK_aisles_client_supplier
    FOREIGN KEY (client_supplier_id) REFERENCES client_suppliers(id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_aisles_client_supplier_id' AND object_id = OBJECT_ID('aisles'))
    CREATE INDEX IX_aisles_client_supplier_id ON aisles(client_supplier_id);
GO

-- v3.0 — Source assets (Épica 4, Documento técnico §7.3)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'source_assets')
BEGIN
    CREATE TABLE source_assets (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        aisle_id VARCHAR(36) NOT NULL,
        type VARCHAR(16) NOT NULL,
        original_filename NVARCHAR(512) NOT NULL,
        storage_path NVARCHAR(1024) NOT NULL,
        storage_provider VARCHAR(16) NULL,
        storage_bucket NVARCHAR(255) NULL,
        storage_key NVARCHAR(1024) NULL,
        content_type VARCHAR(128) NULL,
        file_size_bytes BIGINT NULL,
        etag NVARCHAR(128) NULL,
        mime_type VARCHAR(128) NOT NULL,
        uploaded_at DATETIME2 NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        CONSTRAINT FK_source_assets_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_source_assets_aisle_id ON source_assets(aisle_id);
END;
GO
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
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'capture_session_item_id')
    ALTER TABLE source_assets ADD capture_session_item_id VARCHAR(36) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_source_assets_capture_session_item_id'
      AND object_id = OBJECT_ID('source_assets')
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_source_assets_capture_session_item_id
    ON source_assets(capture_session_item_id)
    WHERE capture_session_item_id IS NOT NULL;
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys WHERE name = 'FK_source_assets_capture_session_item'
)
BEGIN
    ALTER TABLE source_assets
    ADD CONSTRAINT FK_source_assets_capture_session_item
    FOREIGN KEY (capture_session_item_id) REFERENCES capture_session_items(id);
END;
GO

-- v3.0 — Positions (Épica 6, Documento técnico §7.4)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'positions')
BEGIN
    CREATE TABLE positions (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        review_resolution VARCHAR(32) NULL,
        confidence FLOAT NOT NULL,
        needs_review BIT NOT NULL,
        primary_evidence_id VARCHAR(36) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        detected_summary_json NVARCHAR(MAX) NULL,
        corrected_summary_json NVARCHAR(MAX) NULL,
        CONSTRAINT FK_positions_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_positions_aisle_id ON positions(aisle_id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'review_resolution')
    ALTER TABLE positions ADD review_resolution VARCHAR(32) NULL;
GO
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'job_id')
BEGIN
    ALTER TABLE positions ADD job_id VARCHAR(36) NULL;
    ALTER TABLE positions ADD CONSTRAINT FK_positions_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_positions_aisle_job_id' AND object_id = OBJECT_ID('positions'))
    CREATE INDEX IX_positions_aisle_job_id ON positions(aisle_id, job_id);
GO

-- Manual vs automatic creation provenance (mirror 0047).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'creation_source')
BEGIN
    ALTER TABLE positions ADD creation_source VARCHAR(16) NOT NULL
        CONSTRAINT DF_positions_creation_source DEFAULT 'automatic';
END;
GO
IF OBJECT_ID('positions', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_positions_creation_source'
         AND parent_object_id = OBJECT_ID('positions')
   )
BEGIN
    ALTER TABLE positions
        ADD CONSTRAINT CK_positions_creation_source
        CHECK (creation_source IN ('automatic', 'manual'));
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_positions_job_creation_source'
      AND object_id = OBJECT_ID('positions')
)
    CREATE NONCLUSTERED INDEX IX_positions_job_creation_source
        ON positions(job_id, creation_source)
        WHERE job_id IS NOT NULL;
GO

IF OBJECT_ID('position_manual_image_coverage', 'U') IS NULL
BEGIN
    CREATE TABLE position_manual_image_coverage (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        created_by_user_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        job_source_asset_id VARCHAR(36) NOT NULL,
        CONSTRAINT PK_position_manual_image_coverage PRIMARY KEY (id),
        -- (job_id, source_asset_id) keeps one manual result per job photo asset (operator key).
        -- job_source_asset_id uniquely ties the row to the snapshot primary link.
        CONSTRAINT UQ_manual_coverage_job_asset UNIQUE (job_id, source_asset_id),
        CONSTRAINT FK_manual_coverage_position FOREIGN KEY (position_id) REFERENCES positions(id),
        CONSTRAINT FK_manual_coverage_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id),
        CONSTRAINT FK_manual_coverage_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_manual_coverage_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_manual_coverage_job_source_asset
            FOREIGN KEY (job_source_asset_id) REFERENCES job_source_assets(id)
    );
    CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_coverage_job_source_asset
        ON position_manual_image_coverage(job_source_asset_id);
END;
GO

-- v3.0 — Product records (Épica 6, Documento técnico §7.5)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'product_records')
BEGIN
    CREATE TABLE product_records (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        position_id VARCHAR(36) NOT NULL,
        sku NVARCHAR(128) NOT NULL,
        description NVARCHAR(512) NULL,
        detected_quantity INT NOT NULL,
        corrected_quantity INT NULL,
        confidence FLOAT NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_product_records_position FOREIGN KEY (position_id) REFERENCES positions(id)
    );
    CREATE INDEX IX_product_records_position_id ON product_records(position_id);
END;
GO

-- v3.2.2 — Quantity provenance (Minimum Count Rule + qty hardening)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('product_records') AND name = 'qty_source')
    ALTER TABLE product_records ADD qty_source VARCHAR(32) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('product_records') AND name = 'qty_inference_reason')
    ALTER TABLE product_records ADD qty_inference_reason NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('product_records') AND name = 'raw_qty_json')
    ALTER TABLE product_records ADD raw_qty_json NVARCHAR(MAX) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('product_records') AND name = 'qty_parse_status')
    ALTER TABLE product_records ADD qty_parse_status VARCHAR(32) NULL;
GO

-- v3.0 — Evidences (Épica 6, Documento técnico §7.6)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'evidences')
BEGIN
    CREATE TABLE evidences (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        entity_type VARCHAR(32) NOT NULL,
        entity_id VARCHAR(36) NOT NULL,
        type VARCHAR(32) NOT NULL,
        storage_path NVARCHAR(1024) NOT NULL,
        storage_provider VARCHAR(16) NULL,
        storage_bucket NVARCHAR(255) NULL,
        storage_key NVARCHAR(1024) NULL,
        content_type VARCHAR(128) NULL,
        file_size_bytes BIGINT NULL,
        etag NVARCHAR(128) NULL,
        source_asset_id VARCHAR(36) NULL,
        is_primary BIT NOT NULL DEFAULT 0,
        frame_index INT NULL,
        timestamp_ms INT NULL,
        bbox_json NVARCHAR(MAX) NULL,
        quality_score FLOAT NULL
    );
END;
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

-- v3.0 — Review actions (Épica 8, Documento técnico §7.7)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'review_actions')
BEGIN
    CREATE TABLE review_actions (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        position_id VARCHAR(36) NOT NULL,
        action_type VARCHAR(32) NOT NULL,
        before_json NVARCHAR(MAX) NOT NULL,
        after_json NVARCHAR(MAX) NOT NULL,
        created_at DATETIME2 NOT NULL,
        user_id VARCHAR(64) NULL,
        comment NVARCHAR(512) NULL,
        CONSTRAINT FK_review_actions_position FOREIGN KEY (position_id) REFERENCES positions(id)
    );
    CREATE INDEX IX_review_actions_position_id ON review_actions(position_id);
END;
GO

-- Run-scoped review audit: persist inventory job id on each review action (nullable = legacy row).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('review_actions') AND name = 'job_id')
    ALTER TABLE review_actions ADD job_id VARCHAR(36) NULL;
GO

UPDATE ra
SET ra.job_id = p.job_id
FROM review_actions ra
INNER JOIN positions p ON p.id = ra.position_id
WHERE ra.job_id IS NULL AND p.job_id IS NOT NULL;
GO

-- v3.2.3 — Final count records (consolidated quantity from normalized labels)
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
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('final_count_records') AND name = 'job_id')
BEGIN
    ALTER TABLE final_count_records ADD job_id VARCHAR(36) NULL;
    ALTER TABLE final_count_records ADD CONSTRAINT FK_final_count_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_final_count_scope_job' AND object_id = OBJECT_ID('final_count_records'))
    CREATE INDEX IX_final_count_scope_job ON final_count_records(inventory_id, aisle_id, job_id);
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
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('raw_labels') AND name = 'job_id')
BEGIN
    ALTER TABLE raw_labels ADD job_id VARCHAR(36) NULL;
    ALTER TABLE raw_labels ADD CONSTRAINT FK_raw_labels_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_raw_labels_scope_job' AND object_id = OBJECT_ID('raw_labels'))
    CREATE INDEX IX_raw_labels_scope_job ON raw_labels(inventory_id, aisle_id, job_id);
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
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('normalized_labels') AND name = 'job_id')
BEGIN
    ALTER TABLE normalized_labels ADD job_id VARCHAR(36) NULL;
    ALTER TABLE normalized_labels ADD CONSTRAINT FK_normalized_labels_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_normalized_labels_scope_job' AND object_id = OBJECT_ID('normalized_labels'))
    CREATE INDEX IX_normalized_labels_scope_job ON normalized_labels(inventory_id, aisle_id, job_id);
GO

-- Phase C1 — supplier reference images (additive foundation).
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

-- Phase D1 — supplier prompt configs (additive foundation).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'supplier_prompt_configs')
BEGIN
    CREATE TABLE supplier_prompt_configs (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        client_supplier_id VARCHAR(36) NOT NULL,
        provider_name VARCHAR(32) NULL,
        model_name VARCHAR(128) NULL,
        provider_scope_key AS (CASE WHEN provider_name IS NULL THEN '#ALL_PROVIDERS#' ELSE 'P:' + LOWER(provider_name) END) PERSISTED,
        model_scope_key AS (CASE WHEN model_name IS NULL THEN '#ALL_MODELS#' ELSE 'M:' + model_name END) PERSISTED,
        instructions_text NVARCHAR(MAX) NOT NULL,
        version INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_supplier_prompt_configs_is_active DEFAULT (0),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT CK_supplier_prompt_configs_valid_scope
            CHECK (NOT (provider_name IS NULL AND model_name IS NOT NULL)),
        CONSTRAINT FK_supplier_prompt_configs_client_supplier
            FOREIGN KEY (client_supplier_id) REFERENCES client_suppliers(id)
    );
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_supplier_prompt_configs_supplier_scope'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    CREATE INDEX IX_supplier_prompt_configs_supplier_scope
        ON supplier_prompt_configs(client_supplier_id, provider_scope_key, model_scope_key, created_at DESC);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_supplier_prompt_configs_scope_version'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_supplier_prompt_configs_scope_version
        ON supplier_prompt_configs(client_supplier_id, provider_scope_key, model_scope_key, version);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_supplier_prompt_configs_one_active'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_supplier_prompt_configs_one_active
        ON supplier_prompt_configs(client_supplier_id, provider_scope_key, model_scope_key)
        WHERE is_active = 1;
GO

-- Sprint 1 — Field capture sessions (mirror migrations/versions/0016_capture_sessions.sql).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_sessions')
BEGIN
    CREATE TABLE capture_sessions (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        opened_at DATETIME2 NULL,
        closed_at DATETIME2 NULL,
        clock_offset_seconds INT NOT NULL DEFAULT 0,
        CONSTRAINT FK_capture_sessions_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_capture_sessions_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_capture_sessions_inventory_id ON capture_sessions(inventory_id);
    CREATE INDEX IX_capture_sessions_aisle_id ON capture_sessions(aisle_id);
    CREATE INDEX IX_capture_sessions_status_updated ON capture_sessions(status, updated_at);
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID('dbo.capture_sessions')
)
BEGIN
    ;WITH open_ranked AS (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY inventory_id, aisle_id
                ORDER BY created_at ASC, id ASC
            ) AS rn
        FROM dbo.capture_sessions
        WHERE closed_at IS NULL
          AND aisle_id IS NOT NULL
          AND status <> 'cancelled'
          AND status <> 'failed'
          AND status <> 'confirmed'
    )
    UPDATE cs
    SET
        status = 'cancelled',
        closed_at = SYSUTCDATETIME(),
        updated_at = SYSUTCDATETIME()
    FROM dbo.capture_sessions AS cs
    INNER JOIN open_ranked AS r ON r.id = cs.id
    WHERE r.rn > 1;

    CREATE UNIQUE NONCLUSTERED INDEX UQ_capture_sessions_one_open_per_aisle
        ON dbo.capture_sessions (inventory_id, aisle_id)
        WHERE aisle_id IS NOT NULL
          AND closed_at IS NULL
          AND status <> 'cancelled'
          AND status <> 'failed'
          AND status <> 'confirmed';
END;
GO

-- Phase G1 — inventory-level capture sessions (mirror migrations/versions/0020_capture_sessions_inventory_scope.sql).
IF EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_sessions')
      AND name = 'aisle_id'
      AND is_nullable = 0
)
BEGIN
    ALTER TABLE dbo.capture_sessions ALTER COLUMN aisle_id VARCHAR(36) NULL;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_session_items')
BEGIN
    CREATE TABLE capture_session_items (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        staging_storage_key NVARCHAR(1024) NOT NULL,
        content_hash NVARCHAR(128) NULL,
        effective_capture_time DATETIME2 NULL,
        time_source VARCHAR(32) NULL,
        time_confidence FLOAT NULL,
        import_status VARCHAR(32) NOT NULL,
        assignment_status VARCHAR(32) NOT NULL,
        linked_source_asset_id VARCHAR(36) NULL,
        last_error_code VARCHAR(64) NULL,
        last_error_detail NVARCHAR(512) NULL,
        updated_at DATETIME2 NOT NULL,
        original_filename NVARCHAR(512) NULL,
        adjusted_capture_time DATETIME2 NULL,
        assignment_reason NVARCHAR(512) NULL,
        preview_target_position_id VARCHAR(36) NULL,
        CONSTRAINT FK_capture_session_items_session FOREIGN KEY (session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
        CONSTRAINT FK_capture_session_items_source_asset FOREIGN KEY (linked_source_asset_id) REFERENCES source_assets(id)
    );
    CREATE INDEX IX_capture_session_items_session_id ON capture_session_items(session_id);
    CREATE INDEX IX_capture_session_items_linked_asset ON capture_session_items(linked_source_asset_id);
END;
GO

-- Filtered unique: duplicate (session_id, content_hash) disallowed when hash present; NULL hash allowed multiple times.
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_capture_session_items_session_content_hash'
      AND object_id = OBJECT_ID('capture_session_items')
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_capture_session_items_session_content_hash
        ON capture_session_items(session_id, content_hash)
        WHERE content_hash IS NOT NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('capture_session_items') AND name = 'original_filename'
)
    ALTER TABLE capture_session_items ADD original_filename NVARCHAR(512) NULL;
GO

-- Sprint 3 — clock offset + preview columns (mirror migrations/versions/0019_capture_session_sprint3_preview.sql).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_sessions') AND name = 'clock_offset_seconds'
)
    ALTER TABLE dbo.capture_sessions ADD clock_offset_seconds INT NOT NULL DEFAULT 0;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items') AND name = 'adjusted_capture_time'
)
    ALTER TABLE dbo.capture_session_items ADD adjusted_capture_time DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items') AND name = 'assignment_reason'
)
    ALTER TABLE dbo.capture_session_items ADD assignment_reason NVARCHAR(512) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items') AND name = 'preview_target_position_id'
)
    ALTER TABLE dbo.capture_session_items ADD preview_target_position_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_session_confirmations')
BEGIN
    CREATE TABLE capture_session_confirmations (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        idempotency_key NVARCHAR(128) NOT NULL,
        outcome_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_capture_session_confirmations_session FOREIGN KEY (session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
        CONSTRAINT UQ_capture_session_confirmations_session_key UNIQUE (session_id, idempotency_key)
    );
    CREATE INDEX IX_capture_session_confirmations_session_id ON capture_session_confirmations(session_id);
END;
GO

-- G3 — temporal capture groups (mirror migrations/versions/0021_capture_session_groups.sql).
-- FK items→groups: NO ACTION avoids SQL Server 1785 (multiple cascade paths from capture_sessions).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_session_groups')
BEGIN
    CREATE TABLE dbo.capture_session_groups (
        id VARCHAR(36) NOT NULL CONSTRAINT PK_capture_session_groups PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        group_index INT NOT NULL,
        created_at DATETIME2 NOT NULL,
        algorithm_version NVARCHAR(64) NOT NULL,
        CONSTRAINT FK_capture_session_groups_session FOREIGN KEY (session_id) REFERENCES dbo.capture_sessions(id) ON DELETE CASCADE,
        CONSTRAINT UQ_capture_session_groups_session_index UNIQUE (session_id, group_index)
    );
    CREATE INDEX IX_capture_session_groups_session_id ON dbo.capture_session_groups(session_id);
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items')
      AND name = 'group_id'
)
BEGIN
    ALTER TABLE dbo.capture_session_items ADD group_id VARCHAR(36) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_capture_session_items_group'
      AND parent_object_id = OBJECT_ID('dbo.capture_session_items')
)
BEGIN
    ALTER TABLE dbo.capture_session_items
        ADD CONSTRAINT FK_capture_session_items_group
        FOREIGN KEY (group_id) REFERENCES dbo.capture_session_groups(id) ON DELETE NO ACTION;
END;
GO

-- G4 — group → aisle assignment (mirror migrations/versions/0022_capture_session_group_aisle_assignment.sql).
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_groups')
      AND name = 'assigned_aisle_id'
)
BEGIN
    ALTER TABLE dbo.capture_session_groups ADD assigned_aisle_id VARCHAR(36) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_groups')
      AND name = 'assignment_status'
)
BEGIN
    ALTER TABLE dbo.capture_session_groups
        ADD assignment_status NVARCHAR(32) NOT NULL
            CONSTRAINT DF_capture_session_groups_assignment_status DEFAULT ('unassigned');
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_groups')
      AND name = 'assigned_at'
)
BEGIN
    ALTER TABLE dbo.capture_session_groups ADD assigned_at DATETIME2 NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = 'FK_capture_session_groups_assigned_aisle'
      AND parent_object_id = OBJECT_ID('dbo.capture_session_groups')
)
BEGIN
    ALTER TABLE dbo.capture_session_groups
        ADD CONSTRAINT FK_capture_session_groups_assigned_aisle
        FOREIGN KEY (assigned_aisle_id) REFERENCES dbo.aisles(id) ON DELETE NO ACTION;
END;
GO

-- Phase 4.6 — structural entity traceability evidence
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'result_evidence')
BEGIN
    CREATE TABLE result_evidence (
        id VARCHAR(64) NOT NULL PRIMARY KEY,
        job_id VARCHAR(64) NOT NULL,
        inventory_id VARCHAR(64) NOT NULL,
        aisle_id VARCHAR(64) NOT NULL,
        position_id VARCHAR(64) NULL,
        entity_uid VARCHAR(128) NULL,
        model_entity_id VARCHAR(128) NULL,
        raw_manifest_entry_id VARCHAR(64) NULL,
        manifest_entry_id VARCHAR(64) NULL,
        raw_source_image_id VARCHAR(256) NULL,
        resolved_manifest_entry_id VARCHAR(64) NULL,
        source_image_id VARCHAR(256) NULL,
        source_asset_id VARCHAR(64) NULL,
        traceability_status VARCHAR(32) NULL,
        traceability_warning NVARCHAR(1024) NULL,
        role VARCHAR(32) NULL,
        provider VARCHAR(64) NULL,
        model_name VARCHAR(128) NULL,
        schema_version VARCHAR(64) NULL,
        manifest_version INT NULL,
        has_valid_evidence BIT NOT NULL DEFAULT 0,
        evidence_kind VARCHAR(64) NOT NULL DEFAULT 'entity_traceability',
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_result_evidence_job_id ON result_evidence (job_id);
    CREATE INDEX IX_result_evidence_job_entity_uid ON result_evidence (job_id, entity_uid);
    CREATE INDEX IX_result_evidence_job_model_entity_id ON result_evidence (job_id, model_entity_id);
    CREATE INDEX IX_result_evidence_job_traceability_status ON result_evidence (job_id, traceability_status);
    CREATE INDEX IX_result_evidence_job_source_image_id ON result_evidence (job_id, source_image_id);
    CREATE INDEX IX_result_evidence_job_source_asset_id ON result_evidence (job_id, source_asset_id);
    CREATE INDEX IX_result_evidence_job_resolved_manifest_entry_id ON result_evidence (job_id, resolved_manifest_entry_id);
END;
GO
