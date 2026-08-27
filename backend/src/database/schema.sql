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

-- Phase 1 aisle identification override on inventories (mirror 0049).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'identification_mode')
    ALTER TABLE inventories ADD identification_mode VARCHAR(32) NULL;
GO

-- Soft delete (mirror 0096).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'deleted_at')
    ALTER TABLE inventories ADD deleted_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'deleted_by')
    ALTER TABLE inventories ADD deleted_by VARCHAR(64) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE object_id = OBJECT_ID('inventories') AND name = 'IX_inventories_deleted_at'
)
    CREATE NONCLUSTERED INDEX IX_inventories_deleted_at
        ON inventories (deleted_at)
        WHERE deleted_at IS NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_inventories_identification_mode'
)
    ALTER TABLE inventories ADD CONSTRAINT CK_inventories_identification_mode
    CHECK (
        identification_mode IS NULL
        OR identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
    );
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

-- Phase 1 aisle identification — clients.default_identification_mode (mirror 0049/0050).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('clients') AND name = 'default_identification_mode')
    ALTER TABLE clients ADD default_identification_mode VARCHAR(32) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_clients_default_identification_mode'
)
    ALTER TABLE clients ADD CONSTRAINT CK_clients_default_identification_mode
    CHECK (
        default_identification_mode IS NULL
        OR default_identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
    );
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
            execution_id VARCHAR(64) NULL,
            claim_owner_id VARCHAR(64) NULL
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
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'claim_owner_id')
    ALTER TABLE inventory_jobs ADD claim_owner_id VARCHAR(64) NULL;
-- Phase 3 lease fencing (mirror migrations/versions/0072_inventory_jobs_lease_fencing.sql; update both when changing).
-- Reuses claim_owner_id as the lease owner (no duplicate lease_owner_id column).
IF COL_LENGTH('inventory_jobs', 'lease_fencing_token') IS NULL
    ALTER TABLE inventory_jobs ADD lease_fencing_token BIGINT NOT NULL
        CONSTRAINT DF_inventory_jobs_lease_fencing_token DEFAULT (0);
IF COL_LENGTH('inventory_jobs', 'lease_expires_at') IS NULL
    ALTER TABLE inventory_jobs ADD lease_expires_at DATETIME2 NULL;
IF COL_LENGTH('inventory_jobs', 'lease_acquired_at') IS NULL
    ALTER TABLE inventory_jobs ADD lease_acquired_at DATETIME2 NULL;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'IX_inventory_jobs_lease_expiry'
)
    CREATE NONCLUSTERED INDEX IX_inventory_jobs_lease_expiry
        ON inventory_jobs(status, lease_expires_at)
        WHERE lease_expires_at IS NOT NULL;
GO
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

-- Phase 1 aisle identification snapshot (mirror migrations/versions/0049_aisle_identification_mode.sql).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'identification_mode')
    ALTER TABLE inventory_jobs ADD identification_mode VARCHAR(32) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'identification_mode_source')
    ALTER TABLE inventory_jobs ADD identification_mode_source VARCHAR(32) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'configuration_snapshot_version')
    ALTER TABLE inventory_jobs ADD configuration_snapshot_version INT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'execution_strategy')
    ALTER TABLE inventory_jobs ADD execution_strategy VARCHAR(64) NULL;
GO
UPDATE inventory_jobs SET identification_mode = 'LEGACY_LLM' WHERE identification_mode IS NULL;
UPDATE inventory_jobs SET identification_mode_source = 'LEGACY_MIGRATION' WHERE identification_mode_source IS NULL;
UPDATE inventory_jobs SET configuration_snapshot_version = 1 WHERE configuration_snapshot_version IS NULL;
UPDATE inventory_jobs SET execution_strategy = 'LEGACY_LLM' WHERE execution_strategy IS NULL;
GO
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'identification_mode' AND is_nullable = 1)
    ALTER TABLE inventory_jobs ALTER COLUMN identification_mode VARCHAR(32) NOT NULL;
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'identification_mode_source' AND is_nullable = 1)
    ALTER TABLE inventory_jobs ALTER COLUMN identification_mode_source VARCHAR(32) NOT NULL;
GO
IF NOT EXISTS (SELECT * FROM sys.default_constraints WHERE parent_object_id = OBJECT_ID('inventory_jobs') AND name = 'DF_inventory_jobs_identification_mode')
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_identification_mode DEFAULT ('LEGACY_LLM') FOR identification_mode;
IF NOT EXISTS (SELECT * FROM sys.default_constraints WHERE parent_object_id = OBJECT_ID('inventory_jobs') AND name = 'DF_inventory_jobs_identification_mode_source')
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_identification_mode_source DEFAULT ('LEGACY_MIGRATION') FOR identification_mode_source;
IF NOT EXISTS (SELECT * FROM sys.default_constraints WHERE parent_object_id = OBJECT_ID('inventory_jobs') AND name = 'DF_inventory_jobs_configuration_snapshot_version')
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_configuration_snapshot_version DEFAULT (1) FOR configuration_snapshot_version;
IF NOT EXISTS (SELECT * FROM sys.default_constraints WHERE parent_object_id = OBJECT_ID('inventory_jobs') AND name = 'DF_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_execution_strategy DEFAULT ('LEGACY_LLM') FOR execution_strategy;
GO
-- Phase 1 corrections — CHECK constraints (mirror 0050).
IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_identification_mode')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_identification_mode
    CHECK (identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM'));
GO
IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_identification_mode_source')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_identification_mode_source
    CHECK (
        identification_mode_source IN (
            'REQUEST', 'AISLE', 'INVENTORY', 'CLIENT', 'SYSTEM_DEFAULT', 'LEGACY_MIGRATION'
        )
    );
GO
-- Phase 3 (0053) + Phase 4 (0055): execution_strategy CHECK includes CODE_SCAN + INTERNAL_OCR.
IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_execution_strategy
    CHECK (execution_strategy IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN', 'INTERNAL_OCR'));
GO
IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_configuration_snapshot_version')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_configuration_snapshot_version
    CHECK (configuration_snapshot_version > 0);
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

-- Phase 1 aisle identification override on aisles (mirror 0049/0050).
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'identification_mode')
    ALTER TABLE aisles ADD identification_mode VARCHAR(32) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_aisles_identification_mode'
)
    ALTER TABLE aisles ADD CONSTRAINT CK_aisles_identification_mode
    CHECK (
        identification_mode IS NULL
        OR identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
    );
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

-- Phase 1 positioning foundation (mirror 0074 + 0075) — ordered capture + aisle locations.
-- Single block only; do not duplicate Phase 1 positioning DDL elsewhere in this file.
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
            AND (expected_asset_count IS NULL OR expected_asset_count >= 1)
            AND sequence_version >= 1
        )
    );
END
GO

-- Drop obsolete open_aisle_key if a failed 0075 draft left it (SQL Server
-- forbids computed columns in filtered-index predicates — error 10609).
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
      AND name = N'open_aisle_key'
)
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
          AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
    )
        DROP INDEX UQ_ordered_capture_sessions_one_open_per_aisle
            ON dbo.ordered_capture_sessions;

    ALTER TABLE dbo.ordered_capture_sessions DROP COLUMN open_aisle_key;
END
GO

-- 0075: tighten expected_asset_count CHECK (>= 1 when set).
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_ordered_capture_sessions_counts'
      AND parent_object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    ALTER TABLE dbo.ordered_capture_sessions
        DROP CONSTRAINT CK_ordered_capture_sessions_counts;
GO

IF OBJECT_ID(N'dbo.ordered_capture_sessions', N'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = N'CK_ordered_capture_sessions_counts'
          AND parent_object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
   )
    ALTER TABLE dbo.ordered_capture_sessions
        ADD CONSTRAINT CK_ordered_capture_sessions_counts CHECK (
            uploaded_asset_count >= 0
            AND (expected_asset_count IS NULL OR expected_asset_count >= 1)
            AND sequence_version >= 1
        );
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

-- One OPEN/UPLOADING session per aisle (exclusion pattern; no IN/OR in filter).
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ordered_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ordered_capture_sessions_one_open_per_aisle
        ON dbo.ordered_capture_sessions(aisle_id)
        WHERE status <> 'SEALED'
          AND status <> 'PROCESSING'
          AND status <> 'COMPLETED'
          AND status <> 'FAILED';
GO

-- 0076: SEALED→PROCESSING reservation link (nullable FK to inventory_jobs).
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
      AND name = N'processing_job_id'
)
    ALTER TABLE dbo.ordered_capture_sessions ADD processing_job_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_ordered_capture_sessions_processing_job'
)
BEGIN
    ALTER TABLE dbo.ordered_capture_sessions
        ADD CONSTRAINT FK_ordered_capture_sessions_processing_job
        FOREIGN KEY (processing_job_id)
        REFERENCES dbo.inventory_jobs(id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ordered_capture_sessions_processing_job'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    CREATE NONCLUSTERED INDEX IX_ordered_capture_sessions_processing_job
        ON dbo.ordered_capture_sessions(processing_job_id)
        WHERE processing_job_id IS NOT NULL;
GO

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
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'upload_batch_id'
)
    ALTER TABLE dbo.source_assets ADD upload_batch_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.source_assets') AND name = N'upload_client_file_id'
)
    ALTER TABLE dbo.source_assets ADD upload_client_file_id VARCHAR(36) NULL;
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

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.job_source_assets') AND name = N'sequence_number'
)
    ALTER TABLE dbo.job_source_assets ADD sequence_number INT NULL;
GO

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
        idempotency_key VARCHAR(128) NULL,
        idempotency_request_hash VARCHAR(64) NULL,
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

-- 0075 additive path when aisle_location_labels already exists without idempotency cols.
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels')
      AND name = N'idempotency_key'
)
    ALTER TABLE dbo.aisle_location_labels ADD idempotency_key VARCHAR(128) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels')
      AND name = N'idempotency_request_hash'
)
    ALTER TABLE dbo.aisle_location_labels ADD idempotency_request_hash VARCHAR(64) NULL;
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

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_labels_client_idempotency'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_location_labels_client_idempotency
        ON dbo.aisle_location_labels(client_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
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

-- Operator position merge (mirror 0097).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_into_position_id'
)
BEGIN
    ALTER TABLE dbo.positions ADD merged_into_position_id VARCHAR(36) NULL;
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys
    WHERE name = N'FK_positions_merged_into' AND parent_object_id = OBJECT_ID(N'dbo.positions')
)
BEGIN
    ALTER TABLE dbo.positions
        ADD CONSTRAINT FK_positions_merged_into
        FOREIGN KEY (merged_into_position_id) REFERENCES dbo.positions(id);
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_at'
)
BEGIN
    ALTER TABLE dbo.positions ADD merged_at DATETIME2 NULL;
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.check_constraints
    WHERE name = N'CK_positions_merged_into_not_self'
      AND parent_object_id = OBJECT_ID(N'dbo.positions')
)
BEGIN
    ALTER TABLE dbo.positions
        ADD CONSTRAINT CK_positions_merged_into_not_self
        CHECK (
            merged_into_position_id IS NULL
            OR merged_into_position_id <> id
        );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.positions')
      AND name = N'IX_positions_merged_into'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_positions_merged_into
        ON dbo.positions (aisle_id, merged_into_position_id)
        WHERE merged_into_position_id IS NOT NULL;
END
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

-- Phase 2 — job asset processing states + attempts (mirror 0051).
IF OBJECT_ID('job_asset_processing_states', 'U') IS NULL
BEGIN
    CREATE TABLE job_asset_processing_states (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        active_result_id VARCHAR(36) NULL,
        attempt_count INT NOT NULL CONSTRAINT DF_japs_attempt_count DEFAULT (0),
        last_strategy VARCHAR(64) NULL,
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL,
        duration_ms INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        version INT NOT NULL CONSTRAINT DF_japs_version DEFAULT (1),
        execution_scope VARCHAR(32) NULL,
        worker_token VARCHAR(128) NULL,
        lease_expires_at DATETIME2 NULL,
        CONSTRAINT PK_job_asset_processing_states PRIMARY KEY (id),
        CONSTRAINT CK_job_asset_processing_states_status CHECK (
            status IN (
                'PENDING', 'PROCESSING', 'RESOLVED', 'UNRECOGNIZED',
                'FAILED_TECHNICAL', 'PENDING_MANUAL_REVIEW', 'CANCELLED'
            )
        ),
        CONSTRAINT CK_job_asset_processing_states_version CHECK (version > 0),
        CONSTRAINT CK_job_asset_processing_states_attempt_count CHECK (attempt_count >= 0),
        CONSTRAINT CK_job_asset_processing_states_worker_token CHECK (
            worker_token IS NULL OR LEN(worker_token) > 0
        ),
        CONSTRAINT CK_job_asset_processing_states_execution_scope CHECK (
            execution_scope IS NULL OR execution_scope IN ('AISLE_BATCH', 'SINGLE_ASSET')
        )
    );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_job_asset_processing_states_job_asset'
      AND object_id = OBJECT_ID('job_asset_processing_states')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_job_asset_processing_states_job_asset
        ON job_asset_processing_states(job_id, asset_id);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_asset_processing_states_job_status'
      AND object_id = OBJECT_ID('job_asset_processing_states')
)
    CREATE NONCLUSTERED INDEX IX_job_asset_processing_states_job_status
        ON job_asset_processing_states(job_id, status);
GO
IF OBJECT_ID('processing_attempts', 'U') IS NULL
BEGIN
    CREATE TABLE processing_attempts (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        strategy VARCHAR(64) NOT NULL,
        provider VARCHAR(128) NULL,
        model VARCHAR(256) NULL,
        status VARCHAR(32) NOT NULL,
        attempt_number INT NOT NULL,
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL,
        duration_ms INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        raw_result_reference NVARCHAR(1024) NULL,
        normalized_result_json NVARCHAR(MAX) NULL,
        validation_result_json NVARCHAR(MAX) NULL,
        execution_scope VARCHAR(32) NULL,
        logical_asset_attempt BIT NOT NULL CONSTRAINT DF_pa_logical DEFAULT (1),
        configuration_snapshot_version INT NULL,
        parent_batch_attempt_id VARCHAR(36) NULL,
        batch_execution_id VARCHAR(36) NULL,
        worker_token VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NULL,
        CONSTRAINT PK_processing_attempts PRIMARY KEY (id),
        CONSTRAINT CK_processing_attempts_status CHECK (
            status IN (
                'STARTED', 'SUCCEEDED', 'INVALID', 'UNRECOGNIZED',
                'FAILED_TECHNICAL', 'CANCELLED'
            )
        ),
        CONSTRAINT CK_processing_attempts_attempt_number CHECK (attempt_number > 0)
    );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_processing_attempts_job_asset_strategy_n'
      AND object_id = OBJECT_ID('processing_attempts')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_processing_attempts_job_asset_strategy_n
        ON processing_attempts(job_id, asset_id, strategy, attempt_number);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_processing_attempts_job_asset'
      AND object_id = OBJECT_ID('processing_attempts')
)
    CREATE NONCLUSTERED INDEX IX_processing_attempts_job_asset
        ON processing_attempts(job_id, asset_id, attempt_number);
GO

-- Phase 2 corrections — exclusive batch lease + physical batch attempts (mirror 0052).
IF OBJECT_ID('job_processing_leases', 'U') IS NULL
BEGIN
    CREATE TABLE job_processing_leases (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        strategy VARCHAR(64) NOT NULL,
        execution_scope VARCHAR(32) NOT NULL,
        status VARCHAR(16) NOT NULL,
        worker_token VARCHAR(128) NULL,
        acquired_at DATETIME2 NULL,
        heartbeat_at DATETIME2 NULL,
        lease_expires_at DATETIME2 NULL,
        released_at DATETIME2 NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        version INT NOT NULL CONSTRAINT DF_jpl_version DEFAULT (1),
        CONSTRAINT PK_job_processing_leases PRIMARY KEY (id),
        CONSTRAINT CK_job_processing_leases_status CHECK (
            status IN ('AVAILABLE', 'ACQUIRED', 'COMPLETED', 'FAILED', 'CANCELLED')
        ),
        CONSTRAINT CK_job_processing_leases_version CHECK (version > 0)
    );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_job_processing_leases_scope'
      AND object_id = OBJECT_ID('job_processing_leases')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_job_processing_leases_scope
        ON job_processing_leases(job_id, strategy, execution_scope);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_processing_leases_expiry'
      AND object_id = OBJECT_ID('job_processing_leases')
)
    CREATE NONCLUSTERED INDEX IX_job_processing_leases_expiry
        ON job_processing_leases(status, lease_expires_at);
GO

IF OBJECT_ID('batch_processing_attempts', 'U') IS NULL
BEGIN
    CREATE TABLE batch_processing_attempts (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        strategy VARCHAR(64) NOT NULL,
        execution_scope VARCHAR(32) NOT NULL,
        provider VARCHAR(128) NULL,
        model VARCHAR(256) NULL,
        prompt_key VARCHAR(128) NULL,
        prompt_version VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL,
        worker_token VARCHAR(128) NULL,
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL,
        duration_ms INT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_batch_processing_attempts PRIMARY KEY (id),
        CONSTRAINT CK_batch_processing_attempts_status CHECK (
            status IN ('STARTED', 'SUCCEEDED', 'FAILED_TECHNICAL', 'CANCELLED')
        )
    );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_batch_processing_attempts_job_scope_status'
      AND object_id = OBJECT_ID('batch_processing_attempts')
)
    CREATE NONCLUSTERED INDEX IX_batch_processing_attempts_job_scope_status
        ON batch_processing_attempts(job_id, strategy, execution_scope, status);
GO

-- Phase 5 corrections — durable external analysis requests (mirror 0056).
IF OBJECT_ID('external_image_analysis_requests', 'U') IS NULL
BEGIN
    CREATE TABLE external_image_analysis_requests (
        id VARCHAR(36) NOT NULL,
        idempotency_key VARCHAR(256) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        provider VARCHAR(128) NOT NULL,
        model VARCHAR(256) NULL,
        prompt_key VARCHAR(128) NULL,
        prompt_version VARCHAR(64) NULL,
        configuration_snapshot_version INT NULL,
        status VARCHAR(32) NOT NULL,
        attempt_id VARCHAR(36) NULL,
        worker_token VARCHAR(128) NULL,
        request_image_sha256 VARCHAR(64) NULL,
        provider_response_sha256 VARCHAR(64) NULL,
        normalized_result_sha256 VARCHAR(64) NULL,
        normalized_result_json NVARCHAR(MAX) NULL,
        validation_result_json NVARCHAR(MAX) NULL,
        usage_json NVARCHAR(MAX) NULL,
        estimated_cost FLOAT NULL,
        duration_ms INT NULL,
        confidence FLOAT NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        position_id VARCHAR(36) NULL,
        active_result_id VARCHAR(36) NULL,
        client_id VARCHAR(36) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_external_image_analysis_requests PRIMARY KEY (id),
        CONSTRAINT CK_eiar_status CHECK (
            status IN (
                'CLAIMED',
                'IN_FLIGHT',
                'PROVIDER_SUCCEEDED',
                'VALIDATION_FAILED',
                'PERSISTENCE_PENDING',
                'PERSISTED',
                'FAILED_RETRYABLE',
                'FAILED_FINAL',
                'CANCELLED'
            )
        )
    );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_eiar_idempotency_key'
      AND object_id = OBJECT_ID('external_image_analysis_requests')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_eiar_idempotency_key
        ON external_image_analysis_requests(idempotency_key);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_eiar_job_asset'
      AND object_id = OBJECT_ID('external_image_analysis_requests')
)
    CREATE NONCLUSTERED INDEX IX_eiar_job_asset
        ON external_image_analysis_requests(job_id, asset_id, created_at);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_eiar_job_status'
      AND object_id = OBJECT_ID('external_image_analysis_requests')
)
    CREATE NONCLUSTERED INDEX IX_eiar_job_status
        ON external_image_analysis_requests(job_id, status);
GO
IF COL_LENGTH('processing_attempts', 'extra_json') IS NULL
    ALTER TABLE processing_attempts ADD extra_json NVARCHAR(MAX) NULL;
GO
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

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_supplier_reference_annotations_profile'
      AND object_id = OBJECT_ID('supplier_reference_annotations')
)
    CREATE NONCLUSTERED INDEX IX_supplier_reference_annotations_profile
        ON supplier_reference_annotations(profile_id, template_image_id)
        WHERE profile_id IS NOT NULL;
GO

# Soft integrity note: prefer migration 0060b which reconciles inconsistent PERSISTED rows
# then creates CK_external_image_analysis_requests_persisted_result WITH CHECK (trusted).
# Fresh installs may still create WITH CHECK once data is clean.
IF OBJECT_ID('external_image_analysis_requests', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = 'CK_external_image_analysis_requests_persisted_result'
          AND parent_object_id = OBJECT_ID('external_image_analysis_requests')
   )
BEGIN
    ALTER TABLE external_image_analysis_requests WITH CHECK
    ADD CONSTRAINT CK_external_image_analysis_requests_persisted_result
    CHECK (
        status <> 'PERSISTED'
        OR position_id IS NOT NULL
        OR active_result_id IS NOT NULL
    );
END
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

-- end Phase 6 supplier extraction profiles

-- Phase 7 — structured operational processing events (mirror 0059_processing_events.sql).
IF OBJECT_ID('processing_events', 'U') IS NULL
BEGIN
    CREATE TABLE processing_events (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NULL,
        attempt_id VARCHAR(36) NULL,
        event_type VARCHAR(64) NOT NULL,
        severity VARCHAR(16) NOT NULL CONSTRAINT DF_processing_events_severity DEFAULT ('INFO'),
        strategy VARCHAR(64) NULL,
        error_code VARCHAR(128) NULL,
        message NVARCHAR(2000) NULL,
        duration_ms INT NULL,
        correlation_id VARCHAR(64) NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_processing_events PRIMARY KEY (id),
        CONSTRAINT CK_processing_events_severity CHECK (severity IN ('INFO', 'WARN', 'ERROR'))
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_processing_events_job_created'
      AND object_id = OBJECT_ID('processing_events')
)
    CREATE NONCLUSTERED INDEX IX_processing_events_job_created
        ON processing_events(job_id, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_processing_events_job_asset_created'
      AND object_id = OBJECT_ID('processing_events')
)
    CREATE NONCLUSTERED INDEX IX_processing_events_job_asset_created
        ON processing_events(job_id, asset_id, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_processing_events_attempt_created'
      AND object_id = OBJECT_ID('processing_events')
)
    CREATE NONCLUSTERED INDEX IX_processing_events_attempt_created
        ON processing_events(attempt_id, created_at)
        WHERE attempt_id IS NOT NULL;
GO

-- Phase 7 corrections — durable commands + idempotency (mirror 0060).
IF OBJECT_ID('asset_processing_commands', 'U') IS NULL
BEGIN
    CREATE TABLE asset_processing_commands (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        command_type VARCHAR(64) NOT NULL,
        requested_strategy VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL,
        idempotency_key VARCHAR(128) NULL,
        expected_state_version INT NULL,
        actor NVARCHAR(256) NULL,
        reason NVARCHAR(500) NULL,
        payload_json NVARCHAR(MAX) NULL,
        worker_token VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        claimed_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        error_code VARCHAR(128) NULL,
        error_message NVARCHAR(2000) NULL,
        CONSTRAINT PK_asset_processing_commands PRIMARY KEY (id),
        CONSTRAINT CK_apc_status CHECK (
            status IN ('QUEUED', 'CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
        ),
        CONSTRAINT CK_apc_command_type CHECK (
            command_type IN (
                'REPROCESS_FROM_SOURCE',
                'RETRY_PERSISTENCE',
                'SEND_TO_EXTERNAL',
                'RECONCILE_RESULT'
            )
        )
    );
END
GO

IF OBJECT_ID('processing_action_idempotency', 'U') IS NULL
BEGIN
    CREATE TABLE processing_action_idempotency (
        id VARCHAR(36) NOT NULL,
        action_type VARCHAR(64) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        response_json NVARCHAR(MAX) NOT NULL,
        status VARCHAR(32) NOT NULL,
        state_version INT NULL,
        actor NVARCHAR(256) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_processing_action_idempotency PRIMARY KEY (id),
        CONSTRAINT UQ_pai_action_scope_key UNIQUE (action_type, job_id, asset_id, idempotency_key)
    );
END
GO

-- GLOBAL_BATCH durable batch journal (mirror 0061).
IF OBJECT_ID('global_fallback_batch_requests', 'U') IS NULL
BEGIN
    CREATE TABLE global_fallback_batch_requests (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        execution_id VARCHAR(64) NOT NULL,
        attempt INT NOT NULL,
        batch_index INT NOT NULL,
        batch_count INT NOT NULL,
        batch_fingerprint VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        ordered_asset_ids_json NVARCHAR(MAX) NOT NULL,
        provider VARCHAR(128) NOT NULL,
        model VARCHAR(256) NULL,
        schema_version VARCHAR(32) NOT NULL,
        configuration_fingerprint VARCHAR(64) NOT NULL,
        prompt_fingerprint VARCHAR(64) NOT NULL,
        prepared_image_hashes_json NVARCHAR(MAX) NOT NULL,
        provider_request_id VARCHAR(128) NULL,
        response_sha256 VARCHAR(64) NULL,
        normalized_response_json NVARCHAR(MAX) NULL,
        frame_to_asset_map_json NVARCHAR(MAX) NULL,
        merge_plan_json NVARCHAR(MAX) NULL,
        applied_operation_keys_json NVARCHAR(MAX) NULL,
        error_code VARCHAR(64) NULL,
        error_message NVARCHAR(2048) NULL,
        worker_token VARCHAR(128) NULL,
        estimated_cost FLOAT NULL,
        prompt_tokens INT NULL,
        response_tokens INT NULL,
        duration_ms INT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_global_fallback_batch_requests PRIMARY KEY (id),
        CONSTRAINT CK_gfbr_status CHECK (
            status IN (
                'PREPARED',
                'CALLING',
                'RESPONSE_RECEIVED',
                'VALIDATED',
                'PERSISTING',
                'COMPLETED',
                'FAILED_RETRYABLE',
                'FAILED_FINAL',
                'CANCELLED'
            )
        )
    );
END
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_gfbr_job_exec_fingerprint'
      AND object_id = OBJECT_ID('global_fallback_batch_requests')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_gfbr_job_exec_fingerprint
        ON global_fallback_batch_requests(job_id, execution_id, batch_fingerprint);
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_gfbr_job_status'
      AND object_id = OBJECT_ID('global_fallback_batch_requests')
)
    CREATE NONCLUSTERED INDEX IX_gfbr_job_status
        ON global_fallback_batch_requests(job_id, status, batch_index);
GO

-- >>> FOLDED_FROM_MIGRATIONS_BEGIN (auto; keep schema.sql aligned with migrations/versions)
-- Idempotent DDL copied from migrations/versions so clean installs match latest schema.
-- Safe alongside db_migrate apply (IF NOT EXISTS / COL_LENGTH guards).
-- Prefer: update the migration, then re-run this script.

-- ----- folded from 0009_add_position_corrected_code.sql -----
-- v3.3.4 — Persist corrected position code for manual review flow
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'corrected_position_code')
    ALTER TABLE positions ADD corrected_position_code VARCHAR(64) NULL;
GO
GO

-- ----- folded from 0031_global_prompt_configs_foundation.sql -----
-- Phase D9 — global prompt configs persistence foundation (additive only).
-- model_scope_key normalizes NULL model_name to a deterministic scope sentinel.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'global_prompt_configs')
BEGIN
    CREATE TABLE global_prompt_configs (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        scope_type VARCHAR(32) NOT NULL CONSTRAINT DF_global_prompt_configs_scope_type DEFAULT ('global'),
        provider_name VARCHAR(32) NULL,
        model_name VARCHAR(128) NULL,
        model_scope_key AS (CASE WHEN model_name IS NULL THEN '#NULL#' ELSE 'M:' + model_name END) PERSISTED,
        instructions_text NVARCHAR(MAX) NOT NULL,
        version INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_global_prompt_configs_is_active DEFAULT (0),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT CK_global_prompt_configs_scope_type_global
            CHECK (scope_type = 'global'),
        CONSTRAINT CK_global_prompt_configs_global_null_provider_model
            CHECK (scope_type <> 'global' OR (provider_name IS NULL AND model_name IS NULL))
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_global_prompt_configs_scope'
      AND object_id = OBJECT_ID('global_prompt_configs')
)
    CREATE INDEX IX_global_prompt_configs_scope
        ON global_prompt_configs(scope_type, provider_name, model_name, created_at DESC);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_global_prompt_configs_scope_version'
      AND object_id = OBJECT_ID('global_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_global_prompt_configs_scope_version
        ON global_prompt_configs(scope_type, provider_name, model_scope_key, version);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_global_prompt_configs_one_active'
      AND object_id = OBJECT_ID('global_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_global_prompt_configs_one_active
        ON global_prompt_configs(scope_type, provider_name, model_scope_key)
        WHERE is_active = 1;
GO
GO

-- ----- folded from 0033_aisle_code_scans.sql -----
-- Phase 1 — Aisle QR/barcode code scan runs and detections (auxiliary flow; independent of AI worker).

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'aisle_code_scan_runs')
BEGIN
    CREATE TABLE aisle_code_scan_runs (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        total_assets INT NOT NULL,
        processed_assets INT NOT NULL,
        failed_assets INT NOT NULL,
        total_codes_found INT NOT NULL,
        total_qr_found INT NOT NULL,
        total_barcodes_found INT NOT NULL,
        started_at DATETIME2 NOT NULL,
        finished_at DATETIME2 NULL,
        error_message NVARCHAR(2048) NULL,
        scanner_engine VARCHAR(64) NOT NULL,
        is_latest BIT NOT NULL CONSTRAINT DF_aisle_code_scan_runs_is_latest DEFAULT 0,
        created_by VARCHAR(128) NULL,
        metadata_json NVARCHAR(MAX) NULL,
        CONSTRAINT FK_aisle_code_scan_runs_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aisle_code_scan_runs_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_aisle_code_scan_runs_inventory_aisle ON aisle_code_scan_runs(inventory_id, aisle_id);
    CREATE INDEX IX_aisle_code_scan_runs_aisle_started ON aisle_code_scan_runs(aisle_id, started_at);
    CREATE INDEX IX_aisle_code_scan_runs_latest ON aisle_code_scan_runs(inventory_id, aisle_id, is_latest);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'aisle_code_scan_detections')
BEGIN
    CREATE TABLE aisle_code_scan_detections (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        run_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        code_type VARCHAR(16) NOT NULL,
        code_value NVARCHAR(2048) NOT NULL,
        normalized_code_value NVARCHAR(2048) NOT NULL,
        bounding_box_json NVARCHAR(MAX) NULL,
        confidence FLOAT NULL,
        detection_status VARCHAR(32) NOT NULL,
        scanner_engine VARCHAR(64) NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_aisle_code_scan_detections_run FOREIGN KEY (run_id) REFERENCES aisle_code_scan_runs(id),
        CONSTRAINT FK_aisle_code_scan_detections_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aisle_code_scan_detections_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_aisle_code_scan_detections_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_aisle_code_scan_detections_run ON aisle_code_scan_detections(run_id);
    CREATE INDEX IX_aisle_code_scan_detections_asset ON aisle_code_scan_detections(asset_id);
    CREATE INDEX IX_aisle_code_scan_detections_aisle_norm ON aisle_code_scan_detections(aisle_id, normalized_code_value);
    CREATE INDEX IX_aisle_code_scan_detections_scope ON aisle_code_scan_detections(inventory_id, aisle_id);
END;
GO
GO

-- ----- folded from 0034_aisle_code_scan_constraints.sql -----
-- Phase 1 corrections — aisle code scan: one latest run per aisle + enum CHECK constraints.
-- Safe when 0033 was applied without these constraints (idempotent).

-- Replace non-unique latest index with filtered unique index (one is_latest=1 per inventory/aisle).
IF EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_runs_latest' AND object_id = OBJECT_ID('aisle_code_scan_runs')
)
    DROP INDEX IX_aisle_code_scan_runs_latest ON aisle_code_scan_runs;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UX_aisle_code_scan_runs_one_latest' AND object_id = OBJECT_ID('aisle_code_scan_runs')
)
BEGIN
    CREATE UNIQUE INDEX UX_aisle_code_scan_runs_one_latest
    ON aisle_code_scan_runs(inventory_id, aisle_id)
    WHERE is_latest = 1;
END;
GO

-- Run status enum
IF OBJECT_ID('aisle_code_scan_runs', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_runs_status'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_runs')
   )
BEGIN
    ALTER TABLE aisle_code_scan_runs
    ADD CONSTRAINT CK_aisle_code_scan_runs_status CHECK (
        status IN ('running', 'completed', 'completed_with_warnings', 'failed')
    );
END;
GO

-- Detection enums
IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_code_type'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_code_type CHECK (
        code_type IN ('qr', 'barcode', 'datamatrix', 'unknown')
    );
END;
GO

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_detection_status'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_detection_status CHECK (
        detection_status IN ('detected', 'duplicate', 'low_confidence', 'error')
    );
END;
GO
GO

-- ----- folded from 0035_code_scan_detection_matching.sql -----
-- Phase 4 — read-only code scan matching fields on detections (audit snapshot).

IF COL_LENGTH('aisle_code_scan_detections', 'matched_position_id') IS NULL
BEGIN
    ALTER TABLE aisle_code_scan_detections ADD matched_position_id VARCHAR(36) NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_status VARCHAR(32) NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_type VARCHAR(64) NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_confidence FLOAT NULL;
    ALTER TABLE aisle_code_scan_detections ADD match_metadata_json NVARCHAR(MAX) NULL;
    ALTER TABLE aisle_code_scan_detections ADD matched_at DATETIME2 NULL;
END;
GO

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_aisle_code_scan_detections_matched_position'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT FK_aisle_code_scan_detections_matched_position
        FOREIGN KEY (matched_position_id) REFERENCES positions(id);
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_detections_aisle_match_status'
      AND object_id = OBJECT_ID('aisle_code_scan_detections')
)
    CREATE INDEX IX_aisle_code_scan_detections_aisle_match_status
    ON aisle_code_scan_detections(aisle_id, match_status);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_detections_aisle_matched_position'
      AND object_id = OBJECT_ID('aisle_code_scan_detections')
)
    CREATE INDEX IX_aisle_code_scan_detections_aisle_matched_position
    ON aisle_code_scan_detections(aisle_id, matched_position_id);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_aisle_code_scan_detections_run_match_status'
      AND object_id = OBJECT_ID('aisle_code_scan_detections')
)
    CREATE INDEX IX_aisle_code_scan_detections_run_match_status
    ON aisle_code_scan_detections(run_id, match_status);
GO
GO

-- ----- folded from 0036_code_scan_matching_constraints.sql -----
-- Phase 4 corrections — CHECK constraints for code scan match fields.
-- Positions use soft-delete (status=deleted); FK kept without ON DELETE (audit snapshot).

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_match_status'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_match_status
    CHECK (
        match_status IS NULL OR match_status IN (
            'not_evaluated',
            'matched',
            'no_match',
            'multiple_candidates',
            'conflict'
        )
    );
END;
GO

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_match_type'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_match_type
    CHECK (
        match_type IS NULL OR match_type IN (
            'barcode_exact',
            'sku_exact',
            'internal_code_exact',
            'position_code_exact',
            'pallet_id_exact',
            'qr_payload_sku_exact',
            'qr_payload_barcode_exact',
            'multiple_candidates',
            'no_match'
        )
    );
END;
GO
GO

-- ----- folded from 0037_inventory_jobs_finalization_metadata.sql -----
-- Phase 3.2 — Job finalization progress metadata on inventory_jobs
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_status')
    ALTER TABLE inventory_jobs ADD finalization_status VARCHAR(32) NOT NULL DEFAULT 'not_started';
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_finalization_step')
    ALTER TABLE inventory_jobs ADD current_finalization_step VARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'last_completed_finalization_step')
    ALTER TABLE inventory_jobs ADD last_completed_finalization_step VARCHAR(64) NOT NULL DEFAULT 'none';
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_error_code')
    ALTER TABLE inventory_jobs ADD finalization_error_code VARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_error_metadata')
    ALTER TABLE inventory_jobs ADD finalization_error_metadata NVARCHAR(MAX) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_started_at')
    ALTER TABLE inventory_jobs ADD finalization_started_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_completed_at')
    ALTER TABLE inventory_jobs ADD finalization_completed_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'domain_persisted_at')
    ALTER TABLE inventory_jobs ADD domain_persisted_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'artifacts_published_at')
    ALTER TABLE inventory_jobs ADD artifacts_published_at DATETIME2 NULL;
GO
GO

-- ----- folded from 0038_job_finalization_stages_and_artifact_manifest.sql -----
-- Phase 3.3 — Authoritative finalization stage evidence and artifact manifest
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_finalization_stages')
CREATE TABLE job_finalization_stages (
    job_id VARCHAR(64) NOT NULL,
    stage VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    evidence_level VARCHAR(32) NOT NULL DEFAULT 'unknown',
    completed_at DATETIME2 NULL,
    verified_at DATETIME2 NULL,
    verification_source VARCHAR(128) NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error_code VARCHAR(64) NULL,
    last_error_metadata NVARCHAR(MAX) NULL,
    version INT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_job_finalization_stages PRIMARY KEY (job_id, stage)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_stages_job_id')
    CREATE INDEX IX_job_finalization_stages_job_id ON job_finalization_stages (job_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_stages_status_updated')
    CREATE INDEX IX_job_finalization_stages_status_updated ON job_finalization_stages (status, updated_at);

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_artifact_manifest')
CREATE TABLE job_artifact_manifest (
    job_id VARCHAR(64) NOT NULL,
    artifact_kind VARCHAR(64) NOT NULL,
    required BIT NOT NULL DEFAULT 1,
    storage_key VARCHAR(512) NULL,
    content_hash VARCHAR(128) NULL,
    size_bytes BIGINT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    published_at DATETIME2 NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error NVARCHAR(2048) NULL,
    version INT NOT NULL DEFAULT 1,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_job_artifact_manifest PRIMARY KEY (job_id, artifact_kind)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_artifact_manifest_job_id')
    CREATE INDEX IX_job_artifact_manifest_job_id ON job_artifact_manifest (job_id);
GO
GO

-- ----- folded from 0039_job_finalization_recovery_attempts.sql -----
-- Phase 3.4 — Manual finalization recovery audit and lease tracking
-- Foreign keys omitted: job rows may be purged under retention while audit history remains.
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_finalization_recovery_attempts')
CREATE TABLE job_finalization_recovery_attempts (
    id VARCHAR(64) NOT NULL,
    recovery_id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    started_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    finished_at DATETIME2 NULL,
    requested_by VARCHAR(128) NOT NULL,
    source VARCHAR(64) NOT NULL,
    initial_assessment_outcome VARCHAR(64) NOT NULL,
    initial_blocking_reason VARCHAR(128) NULL,
    final_assessment_outcome VARCHAR(64) NULL,
    final_blocking_reason VARCHAR(128) NULL,
    error_code VARCHAR(64) NULL,
    sanitized_error NVARCHAR(2048) NULL,
    lease_expires_at DATETIME2 NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_job_finalization_recovery_attempts PRIMARY KEY (id)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_recovery_attempts_job_id')
    CREATE INDEX IX_job_finalization_recovery_attempts_job_id
        ON job_finalization_recovery_attempts (job_id, started_at DESC);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_job_finalization_recovery_attempts_status')
    CREATE INDEX IX_job_finalization_recovery_attempts_status
        ON job_finalization_recovery_attempts (status, lease_expires_at);
GO
GO

-- ----- folded from 0040_artifact_publication_outbox.sql -----
-- Phase 3.5 — Durable artifact publication outbox
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'artifact_publication_outbox')
CREATE TABLE artifact_publication_outbox (
    id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    artifact_kind VARCHAR(64) NOT NULL,
    required BIT NOT NULL DEFAULT 1,
    source_type VARCHAR(64) NOT NULL DEFAULT 'exact_local_source',
    source_reference NVARCHAR(1024) NULL,
    destination_key VARCHAR(512) NULL,
    content_hash VARCHAR(128) NULL,
    size_bytes BIGINT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at DATETIME2 NULL,
    claimed_at DATETIME2 NULL,
    claimed_by VARCHAR(128) NULL,
    lease_expires_at DATETIME2 NULL,
    last_error_code VARCHAR(64) NULL,
    last_error_message NVARCHAR(2048) NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    published_at DATETIME2 NULL,
    version INT NOT NULL DEFAULT 1,
    CONSTRAINT PK_artifact_publication_outbox PRIMARY KEY (id),
    CONSTRAINT UQ_artifact_publication_outbox_job_kind UNIQUE (job_id, artifact_kind),
    CONSTRAINT CK_artifact_publication_outbox_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT CK_artifact_publication_outbox_max_attempts CHECK (max_attempts > 0),
    CONSTRAINT CK_artifact_publication_outbox_version CHECK (version > 0),
    CONSTRAINT CK_artifact_publication_outbox_size_bytes CHECK (size_bytes IS NULL OR size_bytes >= 0)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_status_next')
    CREATE INDEX IX_artifact_publication_outbox_status_next
        ON artifact_publication_outbox (status, next_attempt_at);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_job_id')
    CREATE INDEX IX_artifact_publication_outbox_job_id
        ON artifact_publication_outbox (job_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_lease_expires')
    CREATE INDEX IX_artifact_publication_outbox_lease_expires
        ON artifact_publication_outbox (lease_expires_at);
GO
GO

-- ----- folded from 0041_artifact_publication_durable_sources_and_checksums.sql -----
-- Phase 3.5 corrections — durable staging checksums and due-work indexing
-- SQL Server requires separate batches: ALTER ADD column, then UPDATE referencing it.

IF COL_LENGTH('artifact_publication_outbox', 'source_sha256') IS NULL
    ALTER TABLE artifact_publication_outbox ADD source_sha256 VARCHAR(128) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'storage_etag') IS NULL
    ALTER TABLE artifact_publication_outbox ADD storage_etag VARCHAR(128) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'storage_checksum_value') IS NULL
    ALTER TABLE artifact_publication_outbox ADD storage_checksum_value VARCHAR(128) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'storage_checksum_algorithm') IS NULL
    ALTER TABLE artifact_publication_outbox ADD storage_checksum_algorithm VARCHAR(32) NULL;
IF COL_LENGTH('artifact_publication_outbox', 'verified_at') IS NULL
    ALTER TABLE artifact_publication_outbox ADD verified_at DATETIME2 NULL;
IF COL_LENGTH('artifact_publication_outbox', 'verification_level') IS NULL
    ALTER TABLE artifact_publication_outbox ADD verification_level VARCHAR(32) NULL;
GO

-- Backfill legacy content_hash into source_sha256 when present
UPDATE artifact_publication_outbox
SET source_sha256 = content_hash
WHERE source_sha256 IS NULL AND content_hash IS NOT NULL;
GO

IF COL_LENGTH('job_artifact_manifest', 'source_sha256') IS NULL
    ALTER TABLE job_artifact_manifest ADD source_sha256 VARCHAR(128) NULL;
IF COL_LENGTH('job_artifact_manifest', 'storage_etag') IS NULL
    ALTER TABLE job_artifact_manifest ADD storage_etag VARCHAR(128) NULL;
IF COL_LENGTH('job_artifact_manifest', 'verification_level') IS NULL
    ALTER TABLE job_artifact_manifest ADD verification_level VARCHAR(32) NULL;
IF COL_LENGTH('job_artifact_manifest', 'verified_at') IS NULL
    ALTER TABLE job_artifact_manifest ADD verified_at DATETIME2 NULL;
GO

UPDATE job_artifact_manifest
SET source_sha256 = content_hash
WHERE source_sha256 IS NULL AND content_hash IS NOT NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_artifact_publication_outbox_status')
    ALTER TABLE artifact_publication_outbox ADD CONSTRAINT CK_artifact_publication_outbox_status
        CHECK (status IN ('pending','claimed','published','retry_scheduled','permanently_failed','canceled'));
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_artifact_publication_outbox_source_type')
    ALTER TABLE artifact_publication_outbox ADD CONSTRAINT CK_artifact_publication_outbox_source_type
        CHECK (source_type IN ('exact_durable_source','exact_local_source','reconstructable','unavailable'));
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_artifact_publication_outbox_due_work')
    CREATE INDEX IX_artifact_publication_outbox_due_work
        ON artifact_publication_outbox (status, next_attempt_at, lease_expires_at)
        INCLUDE (job_id, artifact_kind, version);
GO
GO

-- ----- folded from 0044_source_assets_upload_idempotency.sql -----
-- Additive idempotency keys for aisle source-asset multipart uploads (per request / client file).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'upload_batch_id')
    ALTER TABLE source_assets ADD upload_batch_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'upload_client_file_id')
    ALTER TABLE source_assets ADD upload_client_file_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_source_assets_aisle_upload_batch_client'
      AND object_id = OBJECT_ID('source_assets')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_source_assets_aisle_upload_batch_client
        ON source_assets(aisle_id, upload_batch_id, upload_client_file_id)
        WHERE upload_batch_id IS NOT NULL AND upload_client_file_id IS NOT NULL;
GO
GO

-- ----- folded from 0045_job_source_assets.sql -----
-- Job ↔ source asset snapshot for Observability (historical inputs per job attempt).

IF OBJECT_ID('job_source_assets', 'U') IS NULL
BEGIN
    CREATE TABLE job_source_assets (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        asset_role VARCHAR(32) NOT NULL,
        position_order INT NOT NULL,
        checksum VARCHAR(128) NULL,
        storage_key NVARCHAR(1024) NULL,
        mime_type VARCHAR(255) NULL,
        size_bytes BIGINT NULL,
        width INT NULL,
        height INT NULL,
        stage VARCHAR(64) NULL,
        provider_request_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_job_source_assets PRIMARY KEY (id)
    );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_source_assets_job_order'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE NONCLUSTERED INDEX IX_job_source_assets_job_order
        ON job_source_assets(job_id, position_order, asset_role);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_job_source_assets_job_asset_role'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_job_source_assets_job_asset_role
        ON job_source_assets(job_id, source_asset_id, asset_role);
GO
GO

-- ----- folded from 0046_job_source_assets_original_filename.sql -----
-- Observability corrections — job_source_assets: original filename + versioned-snapshot metadata.
--
-- source_asset_id remains a HISTORICAL reference only (Strategy Option B): source_assets rows may be
-- deleted (retention, aisle mutation) after a job attempt completes, so no FK is added against
-- source_assets(id). job_source_assets is the durable snapshot of what a job attempt actually used;
-- it must remain readable even if the originating source_assets row is gone.

-- 1) original_filename — display name for Observability input catalog (prefer over storage_key basename).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'original_filename'
)
    ALTER TABLE job_source_assets ADD original_filename NVARCHAR(512) NULL;
GO

-- 2) Optional versioned-snapshot / derived-asset columns (additive, all nullable or defaulted).
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'transformation'
)
    ALTER TABLE job_source_assets ADD transformation NVARCHAR(128) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'source_parent_id'
)
    ALTER TABLE job_source_assets ADD source_parent_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'artifact_id'
)
    ALTER TABLE job_source_assets ADD artifact_id VARCHAR(64) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('job_source_assets') AND name = 'snapshot_version'
)
    ALTER TABLE job_source_assets ADD snapshot_version INT NOT NULL
        CONSTRAINT DF_job_source_assets_snapshot_version DEFAULT 1;
GO

-- 3) Integrity: job_id -> inventory_jobs(id) ON DELETE CASCADE (job attempt owns its input snapshot).
-- Guarded on inventory_jobs existing so this migration is safe to run against any deployment order.
IF OBJECT_ID('inventory_jobs', 'U') IS NOT NULL
   AND OBJECT_ID('job_source_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.foreign_keys
       WHERE name = 'FK_job_source_assets_job'
         AND parent_object_id = OBJECT_ID('job_source_assets')
   )
BEGIN
    ALTER TABLE job_source_assets
        ADD CONSTRAINT FK_job_source_assets_job
        FOREIGN KEY (job_id) REFERENCES inventory_jobs(id) ON DELETE CASCADE;
END;
GO

-- 4) Value integrity — defensive CHECK constraints (idempotent).
IF OBJECT_ID('job_source_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_job_source_assets_position_order'
         AND parent_object_id = OBJECT_ID('job_source_assets')
   )
BEGIN
    ALTER TABLE job_source_assets
        ADD CONSTRAINT CK_job_source_assets_position_order CHECK (position_order >= 0);
END;
GO

IF OBJECT_ID('job_source_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_job_source_assets_size_bytes'
         AND parent_object_id = OBJECT_ID('job_source_assets')
   )
BEGIN
    ALTER TABLE job_source_assets
        ADD CONSTRAINT CK_job_source_assets_size_bytes CHECK (size_bytes IS NULL OR size_bytes >= 0);
END;
GO

-- 5) Query support for versioned snapshots (provider_request_id-scoped lookups). Additive only —
-- the existing UQ_job_source_assets_job_asset_role unique index (job_id, source_asset_id, asset_role)
-- is left untouched to avoid breaking current replace-for-job semantics.
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_source_assets_job_provider_request'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE NONCLUSTERED INDEX IX_job_source_assets_job_provider_request
        ON job_source_assets(job_id, provider_request_id, position_order, asset_role);
GO
GO

-- ----- folded from 0047_position_creation_source_and_manual_coverage.sql -----
-- Position creation_source (automatic | manual) + unique manual coverage per (job_id, source_asset_id).
-- Additive / idempotent. Does NOT enforce 1:1 image↔position for automatic results.

-- 1) positions.creation_source
IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('positions') AND name = 'creation_source'
)
BEGIN
    ALTER TABLE positions ADD creation_source VARCHAR(16) NOT NULL
        CONSTRAINT DF_positions_creation_source DEFAULT 'automatic';
END;
GO

-- Backfill any unexpected NULLs (defensive if column was added differently).
IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('positions') AND name = 'creation_source'
)
BEGIN
    UPDATE positions SET creation_source = 'automatic' WHERE creation_source IS NULL OR LTRIM(RTRIM(creation_source)) = '';
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

-- 2) Manual coverage link table — at most one manual result per (job_id, source_asset_id).
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
        CONSTRAINT PK_position_manual_image_coverage PRIMARY KEY (id),
        CONSTRAINT UQ_manual_coverage_job_asset UNIQUE (job_id, source_asset_id),
        CONSTRAINT FK_manual_coverage_position FOREIGN KEY (position_id) REFERENCES positions(id)
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_manual_coverage_position'
      AND object_id = OBJECT_ID('position_manual_image_coverage')
)
    CREATE NONCLUSTERED INDEX IX_manual_coverage_position
        ON position_manual_image_coverage(position_id);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_manual_coverage_job'
      AND object_id = OBJECT_ID('position_manual_image_coverage')
)
    CREATE NONCLUSTERED INDEX IX_manual_coverage_job
        ON position_manual_image_coverage(job_id);
GO

-- 3) Supporting indexes for image↔result resolution (skip if already present).
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_job_source_assets_job_source_asset'
      AND object_id = OBJECT_ID('job_source_assets')
)
    CREATE NONCLUSTERED INDEX IX_job_source_assets_job_source_asset
        ON job_source_assets(job_id, source_asset_id, position_order);
GO

IF OBJECT_ID('result_evidence', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT * FROM sys.indexes
       WHERE name = 'IX_result_evidence_job_source_asset_id'
         AND object_id = OBJECT_ID('result_evidence')
   )
    CREATE NONCLUSTERED INDEX IX_result_evidence_job_source_asset_id
        ON result_evidence(job_id, source_asset_id);
GO

IF OBJECT_ID('result_evidence', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT * FROM sys.indexes
       WHERE name = 'IX_result_evidence_job_source_image_id'
         AND object_id = OBJECT_ID('result_evidence')
   )
    CREATE NONCLUSTERED INDEX IX_result_evidence_job_source_image_id
        ON result_evidence(job_id, source_image_id);
GO
GO

-- ----- folded from 0053_code_scan_processing_strategy.sql -----
-- Phase 3 — CODE_SCAN execution strategy.
-- Additive + idempotent. Widens the inventory_jobs.execution_strategy CHECK to allow
-- 'CODE_SCAN' and adds an optional per-attempt code-scan detections table for audit.
-- Keep aligned with backend/src/database/schema.sql.

-- 1) Guard: reject unknown persisted execution_strategy values before touching the constraint.
IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE execution_strategy NOT IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN')
)
BEGIN
    THROW 50056, 'Invalid inventory_jobs.execution_strategy values found; fix data before 0053 constraint widening.', 1;
END;
GO

-- 2) Recreate the execution_strategy CHECK to include CODE_SCAN (drop-then-add; idempotent).
IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs DROP CONSTRAINT CK_inventory_jobs_execution_strategy;
GO

IF NOT EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy')
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_execution_strategy
    CHECK (execution_strategy IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY', 'CODE_SCAN'));
GO

-- 3) Optional per-attempt code-scan detections audit table (distinct from the sync-API
--    aisle_code_scan_detections table, which is left untouched).
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'job_asset_code_scan_detections')
BEGIN
    CREATE TABLE job_asset_code_scan_detections (
        id VARCHAR(64) NOT NULL PRIMARY KEY,
        job_id VARCHAR(64) NOT NULL,
        asset_id VARCHAR(64) NOT NULL,
        attempt_id VARCHAR(64) NULL,
        detection_index INT NOT NULL,
        symbology VARCHAR(32) NOT NULL,
        normalized_value NVARCHAR(512) NULL,
        raw_value_hash VARCHAR(64) NULL,
        bounding_box_json NVARCHAR(MAX) NULL,
        scanner_name VARCHAR(64) NULL,
        scanner_version VARCHAR(64) NULL,
        preprocessing_variant VARCHAR(32) NULL,
        is_selected BIT NOT NULL DEFAULT (0),
        created_at DATETIME2 NOT NULL DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_job_asset_code_scan_detections_attempt_idx
            UNIQUE (attempt_id, detection_index)
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'IX_job_asset_code_scan_detections_job_asset'
)
    CREATE INDEX IX_job_asset_code_scan_detections_job_asset
    ON job_asset_code_scan_detections (job_id, asset_id);
GO
GO

-- ----- folded from 0060_asset_processing_commands.sql -----
-- Phase 7 corrections: durable asset processing commands + action idempotency.
-- Additive / idempotent for SQL Server.

IF OBJECT_ID('asset_processing_commands', 'U') IS NULL
BEGIN
    CREATE TABLE asset_processing_commands (
        id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        command_type VARCHAR(64) NOT NULL,
        requested_strategy VARCHAR(64) NULL,
        status VARCHAR(32) NOT NULL,
        idempotency_key VARCHAR(128) NULL,
        expected_state_version INT NULL,
        actor NVARCHAR(256) NULL,
        reason NVARCHAR(500) NULL,
        payload_json NVARCHAR(MAX) NULL,
        worker_token VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        claimed_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        error_code VARCHAR(128) NULL,
        error_message NVARCHAR(2000) NULL,
        CONSTRAINT PK_asset_processing_commands PRIMARY KEY (id),
        CONSTRAINT CK_apc_status CHECK (
            status IN ('QUEUED', 'CLAIMED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
        ),
        CONSTRAINT CK_apc_command_type CHECK (
            command_type IN (
                'REPROCESS_FROM_SOURCE',
                'RETRY_PERSISTENCE',
                'SEND_TO_EXTERNAL',
                'RECONCILE_RESULT'
            )
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_apc_job_status_created'
      AND object_id = OBJECT_ID('asset_processing_commands')
)
    CREATE NONCLUSTERED INDEX IX_apc_job_status_created
        ON asset_processing_commands(job_id, status, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_apc_claim_queue'
      AND object_id = OBJECT_ID('asset_processing_commands')
)
    CREATE NONCLUSTERED INDEX IX_apc_claim_queue
        ON asset_processing_commands(status, created_at)
        INCLUDE (job_id, asset_id, command_type)
        WHERE status = 'QUEUED';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_apc_job_asset_created'
      AND object_id = OBJECT_ID('asset_processing_commands')
)
    CREATE NONCLUSTERED INDEX IX_apc_job_asset_created
        ON asset_processing_commands(job_id, asset_id, created_at DESC);
GO

IF OBJECT_ID('processing_action_idempotency', 'U') IS NULL
BEGIN
    CREATE TABLE processing_action_idempotency (
        id VARCHAR(36) NOT NULL,
        action_type VARCHAR(64) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        response_json NVARCHAR(MAX) NOT NULL,
        status VARCHAR(32) NOT NULL,
        state_version INT NULL,
        actor NVARCHAR(256) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_processing_action_idempotency PRIMARY KEY (id),
        CONSTRAINT UQ_pai_action_scope_key UNIQUE (action_type, job_id, asset_id, idempotency_key)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pai_job_asset'
      AND object_id = OBJECT_ID('processing_action_idempotency')
)
    CREATE NONCLUSTERED INDEX IX_pai_job_asset
        ON processing_action_idempotency(job_id, asset_id, created_at DESC);
GO

-- Read-model helpers for operational list (filtered indexes when tables exist).
IF OBJECT_ID('job_asset_processing_states', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_japs_job_status_updated'
          AND object_id = OBJECT_ID('job_asset_processing_states')
   )
    CREATE NONCLUSTERED INDEX IX_japs_job_status_updated
        ON job_asset_processing_states(job_id, status, updated_at DESC);
GO

IF OBJECT_ID('processing_attempts', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pa_job_asset_finished'
          AND object_id = OBJECT_ID('processing_attempts')
   )
    CREATE NONCLUSTERED INDEX IX_pa_job_asset_finished
        ON processing_attempts(job_id, asset_id, finished_at DESC, attempt_number DESC);
GO
GO

-- ----- folded from 0062_mobile_preliminary_detections.sql -----
-- Phase 4: mobile preliminary CODE_SCAN drafts (diagnostic only — not authoritative).
-- Additive / idempotent. Does not touch positions, jobs, or final results.
-- Forward-only: disable ingest via SERVER_PRELIMINARY_DETECTION_INGEST=false.
-- Formal rollback (dev/test only): DROP TABLE IF EXISTS mobile_preliminary_detections;

IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NULL
BEGIN
    CREATE TABLE mobile_preliminary_detections (
        id VARCHAR(36) NOT NULL,
        draft_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        client_file_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        internal_code NVARCHAR(64) NULL,
        quantity INT NULL,
        quantity_status VARCHAR(16) NULL,
        detected_format VARCHAR(32) NULL,
        detected_symbology VARCHAR(32) NULL,
        candidate_count INT NOT NULL CONSTRAINT DF_mpd_candidate_count DEFAULT (0),
        parser_version VARCHAR(32) NOT NULL,
        detector_version VARCHAR(64) NOT NULL,
        prepared_asset_sha256 VARCHAR(80) NOT NULL,
        payload_hash VARCHAR(80) NULL,
        processing_ms INT NULL,
        detected_at DATETIME2 NULL,
        received_at DATETIME2 NOT NULL,
        expires_at DATETIME2 NOT NULL,
        validation_status VARCHAR(32) NOT NULL,
        validation_error_code VARCHAR(64) NULL,
        schema_version VARCHAR(8) NOT NULL CONSTRAINT DF_mpd_schema_version DEFAULT ('1'),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_mobile_preliminary_detections PRIMARY KEY (id),
        CONSTRAINT UQ_mpd_draft_id UNIQUE (draft_id),
        CONSTRAINT UQ_mpd_client_versions_hash UNIQUE (
            client_file_id, detector_version, parser_version, prepared_asset_sha256
        ),
        CONSTRAINT FK_mpd_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_mpd_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_mpd_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id),
        CONSTRAINT CK_mpd_validation_status CHECK (
            validation_status IN ('PENDING_ASSET', 'RECEIVED', 'VALIDATED', 'REJECTED', 'CONFLICT')
        ),
        CONSTRAINT CK_mpd_candidate_count CHECK (candidate_count >= 0),
        CONSTRAINT CK_mpd_quantity CHECK (quantity IS NULL OR quantity > 0),
        CONSTRAINT CK_mpd_status CHECK (
            status IN (
                'RESOLVED', 'UNRESOLVED', 'INVALID', 'AMBIGUOUS', 'FAILED',
                'FAILED_RETRYABLE', 'DETECTED_UNVERIFIED', 'NOT_APPLICABLE'
            )
        )
    );
END
GO

-- Idempotent strengtheners if an earlier Phase-4 table lacked columns/constraints.
IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NOT NULL
   AND COL_LENGTH('mobile_preliminary_detections', 'expires_at') IS NULL
BEGIN
    ALTER TABLE mobile_preliminary_detections ADD expires_at DATETIME2 NULL;
    UPDATE mobile_preliminary_detections
       SET expires_at = DATEADD(day, 90, received_at)
     WHERE expires_at IS NULL;
    ALTER TABLE mobile_preliminary_detections ALTER COLUMN expires_at DATETIME2 NOT NULL;
END
GO

IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = 'CK_mpd_candidate_count'
          AND parent_object_id = OBJECT_ID('mobile_preliminary_detections')
   )
    ALTER TABLE mobile_preliminary_detections
        ADD CONSTRAINT CK_mpd_candidate_count CHECK (candidate_count >= 0);
GO

IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = 'CK_mpd_quantity'
          AND parent_object_id = OBJECT_ID('mobile_preliminary_detections')
   )
    ALTER TABLE mobile_preliminary_detections
        ADD CONSTRAINT CK_mpd_quantity CHECK (quantity IS NULL OR quantity > 0);
GO

IF OBJECT_ID('mobile_preliminary_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = 'FK_mpd_inventory'
          AND parent_object_id = OBJECT_ID('mobile_preliminary_detections')
   )
    ALTER TABLE mobile_preliminary_detections
        ADD CONSTRAINT FK_mpd_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_aisle_received'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_aisle_received
        ON mobile_preliminary_detections(aisle_id, received_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_asset'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_asset
        ON mobile_preliminary_detections(asset_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_client_file'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_client_file
        ON mobile_preliminary_detections(client_file_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_expires_at'
      AND object_id = OBJECT_ID('mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_expires_at
        ON mobile_preliminary_detections(expires_at);
GO
GO

-- ----- folded from 0063_preliminary_detection_reconciliations.sql -----
-- Phase 5: preliminary vs remote reconciliation (diagnostic only).
-- Forward-only. Disable via SERVER_PRELIMINARY_RECONCILIATION=false.
-- Rollback (dev/test): DROP TABLE IF EXISTS preliminary_detection_reconciliations;

IF OBJECT_ID('preliminary_detection_reconciliations', 'U') IS NULL
BEGIN
    CREATE TABLE preliminary_detection_reconciliations (
        id VARCHAR(36) NOT NULL,
        preliminary_detection_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        remote_result_id VARCHAR(36) NULL,
        job_id VARCHAR(36) NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        client_file_id VARCHAR(36) NOT NULL,
        local_status VARCHAR(32) NOT NULL,
        local_internal_code NVARCHAR(64) NULL,
        local_quantity INT NULL,
        remote_status VARCHAR(32) NULL,
        remote_internal_code NVARCHAR(64) NULL,
        remote_quantity INT NULL,
        outcome VARCHAR(64) NOT NULL,
        not_comparable_reason VARCHAR(64) NULL,
        local_parser_version VARCHAR(32) NULL,
        local_detector_version VARCHAR(64) NULL,
        remote_pipeline_version VARCHAR(64) NULL,
        local_detected_at DATETIME2 NULL,
        remote_completed_at DATETIME2 NULL,
        compared_at DATETIME2 NOT NULL,
        comparison_version VARCHAR(16) NOT NULL,
        reconciliation_status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_preliminary_detection_reconciliations PRIMARY KEY (id),
        CONSTRAINT UQ_pdr_preliminary_version UNIQUE (preliminary_detection_id, comparison_version),
        CONSTRAINT FK_pdr_preliminary FOREIGN KEY (preliminary_detection_id)
            REFERENCES mobile_preliminary_detections(id),
        CONSTRAINT FK_pdr_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id),
        CONSTRAINT FK_pdr_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_pdr_reconciliation_status CHECK (
            reconciliation_status IN (
                'PENDING', 'RUNNING', 'COMPLETED', 'NOT_COMPARABLE',
                'RETRY_SCHEDULED', 'FAILED_TERMINAL'
            )
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_inventory_aisle'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_inventory_aisle
        ON preliminary_detection_reconciliations(inventory_id, aisle_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_aisle_compared'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_aisle_compared
        ON preliminary_detection_reconciliations(aisle_id, compared_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_asset'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_asset
        ON preliminary_detection_reconciliations(asset_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_outcome'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_outcome
        ON preliminary_detection_reconciliations(outcome);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_client_file'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_client_file
        ON preliminary_detection_reconciliations(client_file_id);
GO
GO

-- ----- folded from 0064_preliminary_reconciliation_corrections.sql -----
-- Phase 5 corrections: reconciliation identity, lease/retry, revision, FKs.
-- Forward-only additive on 0063. Do not edit 0063 if already applied.
-- Rollback (dev/test): drop new columns/constraints carefully or DROP TABLE.

-- Drop old unique (preliminary + version only) if present.
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'UQ_pdr_preliminary_version'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    ALTER TABLE preliminary_detection_reconciliations
        DROP CONSTRAINT UQ_pdr_preliminary_version;
GO

-- job_id required for identity (backfill empty → keep nullable then constrain new rows in app).
IF COL_LENGTH('preliminary_detection_reconciliations', 'remote_result_fingerprint') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD remote_result_fingerprint VARCHAR(80) NOT NULL
            CONSTRAINT DF_pdr_remote_fp DEFAULT ('PENDING');
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'revision') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD revision INT NOT NULL CONSTRAINT DF_pdr_revision DEFAULT (1);
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'supersedes_id') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD supersedes_id VARCHAR(36) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'row_version') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD row_version INT NOT NULL CONSTRAINT DF_pdr_row_version DEFAULT (1);
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'attempt_count') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD attempt_count INT NOT NULL CONSTRAINT DF_pdr_attempt_count DEFAULT (0);
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'next_retry_at') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD next_retry_at DATETIME2 NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'lease_token') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD lease_token VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'lease_expires_at') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD lease_expires_at DATETIME2 NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'last_error_code') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD last_error_code VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'app_version') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD app_version VARCHAR(32) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'device_model') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD device_model VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'preparation_profile') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD preparation_profile VARCHAR(64) NULL;
GO

IF COL_LENGTH('preliminary_detection_reconciliations', 'expires_at') IS NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD expires_at DATETIME2 NULL;
GO

-- Identity supporting reprocess: one row per draft + comparison_version + job.
IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'UQ_pdr_preliminary_version_job'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
BEGIN
    -- Normalize NULL job_id for unique (should not happen for new rows).
    UPDATE preliminary_detection_reconciliations
       SET job_id = 'LEGACY-UNKNOWN'
     WHERE job_id IS NULL;

    ALTER TABLE preliminary_detection_reconciliations
        ALTER COLUMN job_id VARCHAR(36) NOT NULL;

    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT UQ_pdr_preliminary_version_job
            UNIQUE (preliminary_detection_id, comparison_version, job_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_pdr_inventory'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT FK_pdr_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = 'FK_pdr_job'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
) AND OBJECT_ID('inventory_jobs', 'U') IS NOT NULL
    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT FK_pdr_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_pdr_not_comparable_reason'
      AND parent_object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    ALTER TABLE preliminary_detection_reconciliations
        ADD CONSTRAINT CK_pdr_not_comparable_reason CHECK (
            (outcome <> 'NOT_COMPARABLE' AND not_comparable_reason IS NULL)
            OR (outcome = 'NOT_COMPARABLE' AND not_comparable_reason IS NOT NULL)
            OR reconciliation_status IN ('PENDING', 'RUNNING', 'RETRY_SCHEDULED')
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_worker_due'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_worker_due
        ON preliminary_detection_reconciliations(reconciliation_status, next_retry_at)
        INCLUDE (lease_expires_at, attempt_count);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_job'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_job
        ON preliminary_detection_reconciliations(job_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_pdr_expires'
      AND object_id = OBJECT_ID('preliminary_detection_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_pdr_expires
        ON preliminary_detection_reconciliations(expires_at)
        WHERE expires_at IS NOT NULL;
GO
GO

-- ----- folded from 0065_authoritative_local_code_scan_results.sql -----
-- Intermediate phase: operator-confirmed local CODE_SCAN results (authoritative).
-- Additive / idempotent. Positions applied at /process via ProcessingResultPersister.
-- Forward-only: disable via SERVER_AUTHORITATIVE_LOCAL_CODE_SCAN_INGEST=false.
-- Formal rollback (dev/test only): DROP TABLE IF EXISTS authoritative_local_code_scan_results;
--
-- Window: AUTHORITATIVE_SYNCED (row stored) → FINAL_POSITION_APPLIED (applied_at set at /process).

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_local_code_scan_results (
        id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        client_file_id VARCHAR(36) NOT NULL,
        result_version INT NOT NULL,
        supersedes_result_id VARCHAR(36) NULL,
        is_current BIT NOT NULL CONSTRAINT DF_alcsr_is_current DEFAULT (1),
        internal_code NVARCHAR(64) NOT NULL,
        quantity INT NULL,
        quantity_status VARCHAR(16) NOT NULL,
        source VARCHAR(32) NOT NULL,
        detected_internal_code NVARCHAR(64) NULL,
        detected_quantity INT NULL,
        detected_symbology VARCHAR(32) NULL,
        parser_version VARCHAR(32) NOT NULL,
        detector_version VARCHAR(64) NOT NULL,
        prepared_asset_sha256 VARCHAR(80) NOT NULL,
        content_hash VARCHAR(80) NOT NULL,
        confirmed_by VARCHAR(36) NOT NULL,
        client_confirmed_at DATETIME2 NULL,
        server_confirmed_at DATETIME2 NOT NULL,
        server_received_at DATETIME2 NOT NULL,
        confirmed_at DATETIME2 NOT NULL, -- = server_confirmed_at (compat)
        applied_job_id VARCHAR(36) NULL,
        applied_at DATETIME2 NULL,
        row_version INT NOT NULL CONSTRAINT DF_alcsr_row_version DEFAULT (1),
        schema_version VARCHAR(8) NOT NULL CONSTRAINT DF_alcsr_schema_version DEFAULT ('1'),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_authoritative_local_code_scan_results PRIMARY KEY (id),
        CONSTRAINT UQ_alcsr_asset_version UNIQUE (asset_id, result_version),
        CONSTRAINT FK_alcsr_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_alcsr_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT FK_alcsr_asset FOREIGN KEY (asset_id) REFERENCES source_assets(id),
        CONSTRAINT CK_alcsr_result_version CHECK (result_version >= 1),
        CONSTRAINT CK_alcsr_quantity CHECK (quantity IS NULL OR quantity > 0),
        CONSTRAINT CK_alcsr_quantity_status CHECK (
            quantity_status IN ('PRESENT', 'MISSING')
        ),
        CONSTRAINT CK_alcsr_source CHECK (
            source IN ('LOCAL_CODE_SCAN', 'LOCAL_MANUAL_CORRECTION')
        ),
        CONSTRAINT CK_alcsr_qty_consistency CHECK (
            (quantity_status = 'PRESENT' AND quantity IS NOT NULL AND quantity > 0)
            OR (quantity_status = 'MISSING' AND quantity IS NULL)
        )
    );
END
GO

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_alcsr_aisle_current'
          AND object_id = OBJECT_ID('authoritative_local_code_scan_results')
   )
    CREATE INDEX IX_alcsr_aisle_current
        ON authoritative_local_code_scan_results (inventory_id, aisle_id, is_current);
GO

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_alcsr_asset_current'
          AND object_id = OBJECT_ID('authoritative_local_code_scan_results')
   )
    CREATE INDEX IX_alcsr_asset_current
        ON authoritative_local_code_scan_results (asset_id, is_current);
GO

IF OBJECT_ID('authoritative_local_code_scan_results', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_alcsr_asset_current'
          AND object_id = OBJECT_ID('authoritative_local_code_scan_results')
   )
    CREATE UNIQUE INDEX UQ_alcsr_asset_current
        ON authoritative_local_code_scan_results (asset_id)
        WHERE is_current = 1;
GO

-- Note: mobile_preliminary_detections.confirmed_result_id intentionally NOT added;
-- preliminary drafts remain diagnostic-only; link via client_file_id / asset_id when needed.
GO

-- ----- folded from 0066_authoritative_aisle_finalization.sql -----
-- Phase 6: authoritative aisle finalization (local CODE_SCAN close without remote reprocess).
-- Additive / idempotent. Disable via SERVER_AUTHORITATIVE_AISLE_FINALIZATION=false.
-- Formal rollback (dev/test only):
--   DROP TABLE IF EXISTS authoritative_aisle_finalization_items;
--   DROP TABLE IF EXISTS authoritative_aisle_finalization_locks;
--   DROP TABLE IF EXISTS authoritative_aisle_excluded_assets;
--   DROP TABLE IF EXISTS authoritative_aisle_finalizations;

IF OBJECT_ID('authoritative_aisle_finalizations', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_finalizations (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        capture_session_id VARCHAR(36) NULL,
        finalization_version INT NOT NULL,
        status VARCHAR(40) NOT NULL,
        total_assets INT NOT NULL,
        applied_assets INT NOT NULL,
        excluded_assets INT NOT NULL,
        position_count INT NOT NULL,
        expected_asset_count INT NULL,
        content_hash VARCHAR(80) NOT NULL,
        confirmed_by VARCHAR(36) NOT NULL,
        confirmed_at DATETIME2 NOT NULL,
        completed_at DATETIME2 NULL,
        is_current BIT NOT NULL CONSTRAINT DF_aaf_is_current DEFAULT (1),
        row_version INT NOT NULL CONSTRAINT DF_aaf_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_authoritative_aisle_finalizations PRIMARY KEY (id),
        CONSTRAINT UQ_aaf_aisle_version UNIQUE (aisle_id, finalization_version),
        CONSTRAINT FK_aaf_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aaf_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_aaf_finalization_version CHECK (finalization_version >= 1),
        CONSTRAINT CK_aaf_counts CHECK (
            total_assets >= 0 AND applied_assets >= 0 AND excluded_assets >= 0
            AND position_count >= 0
            AND applied_assets + excluded_assets <= total_assets
        ),
        CONSTRAINT CK_aaf_status CHECK (
            status IN (
                'FINALIZING',
                'COMPLETED_BY_LOCAL_AUTHORITY',
                'FINALIZATION_FAILED',
                'CANCELED'
            )
        )
    );
END
GO

IF OBJECT_ID('authoritative_aisle_finalizations', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_aaf_aisle_current'
          AND object_id = OBJECT_ID('authoritative_aisle_finalizations')
   )
    CREATE UNIQUE INDEX IX_aaf_aisle_current
        ON authoritative_aisle_finalizations (aisle_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('authoritative_aisle_finalization_items', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_finalization_items (
        id VARCHAR(36) NOT NULL,
        finalization_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        authoritative_result_id VARCHAR(36) NULL,
        position_id VARCHAR(36) NULL,
        item_status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aafi PRIMARY KEY (id),
        CONSTRAINT UQ_aafi_finalization_asset UNIQUE (finalization_id, asset_id),
        CONSTRAINT FK_aafi_finalization FOREIGN KEY (finalization_id)
            REFERENCES authoritative_aisle_finalizations(id),
        CONSTRAINT CK_aafi_item_status CHECK (
            item_status IN ('CONFIRMED_AND_APPLIED', 'EXCLUDED')
        )
    );
END
GO

IF OBJECT_ID('authoritative_aisle_finalization_items', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_aafi_finalization'
          AND object_id = OBJECT_ID('authoritative_aisle_finalization_items')
   )
    CREATE INDEX IX_aafi_finalization
        ON authoritative_aisle_finalization_items (finalization_id);
GO

IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_excluded_assets (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        reason VARCHAR(40) NOT NULL,
        excluded_by VARCHAR(36) NOT NULL,
        excluded_at DATETIME2 NOT NULL,
        is_current BIT NOT NULL CONSTRAINT DF_aaea_is_current DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aaea PRIMARY KEY (id),
        CONSTRAINT FK_aaea_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aaea_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_aaea_reason CHECK (
            reason IN (
                'DUPLICATE_PHOTO',
                'INVALID_PHOTO',
                'NOT_INVENTORY_LABEL',
                'USER_EXCLUDED',
                'CAPTURE_ERROR'
            )
        )
    );
END
GO

IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_aaea_aisle_asset_current'
          AND object_id = OBJECT_ID('authoritative_aisle_excluded_assets')
   )
    CREATE UNIQUE INDEX UQ_aaea_aisle_asset_current
        ON authoritative_aisle_excluded_assets (aisle_id, asset_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_aaea_aisle_current'
          AND object_id = OBJECT_ID('authoritative_aisle_excluded_assets')
   )
    CREATE INDEX IX_aaea_aisle_current
        ON authoritative_aisle_excluded_assets (inventory_id, aisle_id, is_current);
GO

IF OBJECT_ID('authoritative_aisle_finalization_locks', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_finalization_locks (
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        owner_token VARCHAR(64) NOT NULL,
        lease_expires_at DATETIME2 NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aafl PRIMARY KEY (aisle_id),
        CONSTRAINT FK_aafl_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aafl_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
END
GO
GO

-- ----- folded from 0067_server_reprocess_runs.sql -----
-- Phase 7: optional server reprocess (proposals; no automatic overwrite of current results).
-- Additive / idempotent. Disable via SERVER_SERVER_REPROCESS=false.
-- Formal rollback (dev/test only):
--   DROP TABLE IF EXISTS server_reprocess_adoption_items;
--   DROP TABLE IF EXISTS server_reprocess_adoptions;
--   DROP TABLE IF EXISTS server_reprocess_proposals;
--   DROP TABLE IF EXISTS server_reprocess_run_assets;
--   DROP TABLE IF EXISTS server_reprocess_runs;
--   DROP TABLE IF EXISTS server_reprocess_locks;

IF OBJECT_ID('server_reprocess_runs', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_runs (
        id VARCHAR(36) NOT NULL,
        request_id VARCHAR(64) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        source_session_id VARCHAR(36) NULL,
        company_id VARCHAR(36) NULL,
        run_type VARCHAR(40) NOT NULL,
        strategy VARCHAR(40) NULL,
        scope_type VARCHAR(40) NOT NULL,
        scope_json NVARCHAR(MAX) NOT NULL,
        snapshot_json NVARCHAR(MAX) NOT NULL,
        processing_mode VARCHAR(40) NOT NULL,
        reason VARCHAR(80) NOT NULL,
        status VARCHAR(32) NOT NULL,
        review_status VARCHAR(40) NOT NULL,
        requested_by VARCHAR(36) NOT NULL,
        requested_at DATETIME2 NOT NULL,
        started_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        canceled_at DATETIME2 NULL,
        failed_at DATETIME2 NULL,
        failure_code VARCHAR(80) NULL,
        failure_message NVARCHAR(500) NULL,
        pipeline_version VARCHAR(64) NULL,
        model_version VARCHAR(64) NULL,
        prompt_version VARCHAR(64) NULL,
        supplier_profile_id VARCHAR(36) NULL,
        linked_job_id VARCHAR(36) NULL,
        has_prior_authority BIT NOT NULL CONSTRAINT DF_srr_has_prior DEFAULT (1),
        row_version INT NOT NULL CONSTRAINT DF_srr_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_runs PRIMARY KEY (id),
        CONSTRAINT UQ_srr_request_id UNIQUE (request_id),
        CONSTRAINT FK_srr_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_srr_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_srr_run_type CHECK (
            run_type IN (
                'INITIAL_SERVER_PROCESSING',
                'SERVER_REPROCESS',
                'LOCAL_AUTHORITY_APPLY'
            )
        ),
        CONSTRAINT CK_srr_scope_type CHECK (
            scope_type IN (
                'FULL_AISLE',
                'SELECTED_ASSETS',
                'FAILED_ONLY',
                'UNRECOGNIZED_ONLY',
                'PENDING_REVIEW_ONLY'
            )
        ),
        CONSTRAINT CK_srr_status CHECK (
            status IN (
                'REQUESTED',
                'QUEUED',
                'RUNNING',
                'COMPLETED',
                'FAILED',
                'CANCELED',
                'TIMED_OUT',
                'PARTIAL'
            )
        ),
        CONSTRAINT CK_srr_review_status CHECK (
            review_status IN (
                'NOT_REVIEWED',
                'REVIEW_IN_PROGRESS',
                'REVIEW_COMPLETED',
                'DISCARDED',
                'ADOPTED_PARTIALLY',
                'ADOPTED_COMPLETELY'
            )
        ),
        CONSTRAINT CK_srr_processing_mode CHECK (
            processing_mode IN (
                'CODE_SCAN',
                'INTERNAL_OCR',
                'GLOBAL_FALLBACK',
                'AUTO_PIPELINE'
            )
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_runs', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srr_aisle_requested'
          AND object_id = OBJECT_ID('server_reprocess_runs')
   )
    CREATE INDEX IX_srr_aisle_requested
        ON server_reprocess_runs (aisle_id, requested_at DESC);
GO

IF OBJECT_ID('server_reprocess_run_assets', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_run_assets (
        id VARCHAR(36) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        asset_hash VARCHAR(128) NULL,
        previous_result_id VARCHAR(36) NULL,
        previous_position_id VARCHAR(36) NULL,
        previous_internal_code NVARCHAR(128) NULL,
        previous_quantity DECIMAL(18, 4) NULL,
        previous_resolved BIT NOT NULL CONSTRAINT DF_srra_prev_resolved DEFAULT (0),
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_run_assets PRIMARY KEY (id),
        CONSTRAINT UQ_srra_run_asset UNIQUE (run_id, asset_id),
        CONSTRAINT FK_srra_run FOREIGN KEY (run_id) REFERENCES server_reprocess_runs(id)
    );
END
GO

IF OBJECT_ID('server_reprocess_run_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srra_run'
          AND object_id = OBJECT_ID('server_reprocess_run_assets')
   )
    CREATE INDEX IX_srra_run ON server_reprocess_run_assets (run_id);
GO

IF OBJECT_ID('server_reprocess_proposals', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_proposals (
        id VARCHAR(36) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        remote_result_id VARCHAR(36) NULL,
        previous_result_id VARCHAR(36) NULL,
        previous_position_id VARCHAR(36) NULL,
        status VARCHAR(40) NOT NULL,
        difference_type VARCHAR(64) NOT NULL,
        internal_code NVARCHAR(128) NULL,
        quantity DECIMAL(18, 4) NULL,
        confidence FLOAT NULL,
        source VARCHAR(64) NULL,
        pipeline_version VARCHAR(64) NULL,
        remote_resolved BIT NOT NULL CONSTRAINT DF_srp_remote_resolved DEFAULT (0),
        review_status VARCHAR(40) NOT NULL CONSTRAINT DF_srp_review DEFAULT ('NOT_REVIEWED'),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_proposals PRIMARY KEY (id),
        CONSTRAINT UQ_srp_run_asset UNIQUE (run_id, asset_id),
        CONSTRAINT FK_srp_run FOREIGN KEY (run_id) REFERENCES server_reprocess_runs(id),
        CONSTRAINT CK_srp_status CHECK (
            status IN (
                'PROPOSED',
                'ADOPTED',
                'KEPT_CURRENT',
                'DEFERRED',
                'DISCARDED',
                'STALE',
                'NOT_COMPARABLE'
            )
        ),
        CONSTRAINT CK_srp_difference CHECK (
            difference_type IN (
                'SAME_RESULT',
                'CODE_CHANGED',
                'QUANTITY_CHANGED',
                'CODE_AND_QUANTITY_CHANGED',
                'PREVIOUS_UNRESOLVED_REMOTE_RESOLVED',
                'PREVIOUS_RESOLVED_REMOTE_UNRESOLVED',
                'REMOTE_AMBIGUOUS',
                'NO_PREVIOUS_RESULT',
                'NOT_COMPARABLE',
                'NOT_COMPARABLE_GLOBAL_BATCH'
            )
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_proposals', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srp_run_diff'
          AND object_id = OBJECT_ID('server_reprocess_proposals')
   )
    CREATE INDEX IX_srp_run_diff
        ON server_reprocess_proposals (run_id, difference_type);
GO

IF OBJECT_ID('server_reprocess_adoptions', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_adoptions (
        id VARCHAR(36) NOT NULL,
        adoption_id VARCHAR(64) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        adopted_by VARCHAR(36) NOT NULL,
        adopted_at DATETIME2 NOT NULL,
        item_count INT NOT NULL,
        adopted_count INT NOT NULL,
        kept_count INT NOT NULL,
        deferred_count INT NOT NULL,
        row_version INT NOT NULL CONSTRAINT DF_sra_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_adoptions PRIMARY KEY (id),
        CONSTRAINT UQ_sra_adoption_id UNIQUE (adoption_id),
        CONSTRAINT FK_sra_run FOREIGN KEY (run_id) REFERENCES server_reprocess_runs(id),
        CONSTRAINT CK_sra_status CHECK (
            status IN ('COMPLETED', 'FAILED', 'ROLLED_BACK')
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_adoption_items', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_adoption_items (
        id VARCHAR(36) NOT NULL,
        adoption_row_id VARCHAR(36) NOT NULL,
        proposal_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        action VARCHAR(32) NOT NULL,
        expected_previous_result_id VARCHAR(36) NULL,
        new_result_id VARCHAR(36) NULL,
        new_position_id VARCHAR(36) NULL,
        edit_internal_code NVARCHAR(128) NULL,
        edit_quantity DECIMAL(18, 4) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_adoption_items PRIMARY KEY (id),
        CONSTRAINT UQ_srai_adoption_proposal UNIQUE (adoption_row_id, proposal_id),
        CONSTRAINT FK_srai_adoption FOREIGN KEY (adoption_row_id)
            REFERENCES server_reprocess_adoptions(id),
        CONSTRAINT FK_srai_proposal FOREIGN KEY (proposal_id)
            REFERENCES server_reprocess_proposals(id),
        CONSTRAINT CK_srai_action CHECK (
            action IN ('ADOPT', 'KEEP_CURRENT', 'EDIT_AND_ADOPT', 'DEFER')
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_locks', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_locks (
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        owner_token VARCHAR(64) NOT NULL,
        expires_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_locks PRIMARY KEY (aisle_id)
    );
END
GO
GO

-- ----- folded from 0068_server_reprocess_adoption_content_hash.sql -----
-- Phase 7 corrections: adoption content_hash for idempotent payload replay.
-- Additive. Do not alter 0067 if already applied.
-- Formal rollback (dev/test only):
--   ALTER TABLE server_reprocess_adoptions DROP CONSTRAINT UQ_sra_adoption_hash;
--   ALTER TABLE server_reprocess_adoptions DROP COLUMN content_hash;

IF OBJECT_ID('server_reprocess_adoptions', 'U') IS NOT NULL
   AND COL_LENGTH('server_reprocess_adoptions', 'content_hash') IS NULL
BEGIN
    ALTER TABLE server_reprocess_adoptions
        ADD content_hash VARCHAR(80) NOT NULL
            CONSTRAINT DF_sra_content_hash DEFAULT ('');
END
GO

IF OBJECT_ID('server_reprocess_adoptions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_sra_run_content_hash'
          AND object_id = OBJECT_ID('server_reprocess_adoptions')
   )
    CREATE INDEX IX_sra_run_content_hash
        ON server_reprocess_adoptions (run_id, content_hash);
GO

IF OBJECT_ID('server_reprocess_runs', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srr_aisle_status'
          AND object_id = OBJECT_ID('server_reprocess_runs')
   )
    CREATE INDEX IX_srr_aisle_status
        ON server_reprocess_runs (aisle_id, status, requested_at DESC);
GO
GO

-- ----- folded from 0069_aisle_revisions_phase8.sql -----
-- Phase 8: aisle revisions, position versions, finalization lineage.
-- Additive / idempotent. Disable via SERVER_AISLE_REVISIONS=false.
-- Formal rollback (dev/test only):
--   DROP TABLE IF EXISTS aisle_revision_items;
--   DROP TABLE IF EXISTS aisle_revision_locks;
--   DROP TABLE IF EXISTS aisle_revisions;
--   DROP TABLE IF EXISTS position_versions;
--   ALTER TABLE authoritative_aisle_finalizations DROP COLUMN supersedes_finalization_id;
--   ALTER TABLE authoritative_aisle_finalizations DROP COLUMN revision_id;
--   ALTER TABLE aisles DROP COLUMN revision_status;

IF COL_LENGTH('aisles', 'revision_status') IS NULL
BEGIN
    ALTER TABLE aisles ADD revision_status VARCHAR(32) NULL;
END
GO

IF COL_LENGTH('authoritative_aisle_finalizations', 'supersedes_finalization_id') IS NULL
BEGIN
    ALTER TABLE authoritative_aisle_finalizations
        ADD supersedes_finalization_id VARCHAR(36) NULL;
END
GO

IF COL_LENGTH('authoritative_aisle_finalizations', 'revision_id') IS NULL
BEGIN
    ALTER TABLE authoritative_aisle_finalizations
        ADD revision_id VARCHAR(36) NULL;
END
GO

IF OBJECT_ID('position_versions', 'U') IS NULL
BEGIN
    CREATE TABLE position_versions (
        id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NOT NULL,
        version INT NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        internal_code VARCHAR(128) NOT NULL,
        quantity INT NULL,
        result_id VARCHAR(36) NULL,
        is_current BIT NOT NULL CONSTRAINT DF_pv_is_current DEFAULT (1),
        supersedes_position_version_id VARCHAR(36) NULL,
        revision_id VARCHAR(36) NULL,
        revision_item_id VARCHAR(36) NULL,
        created_by VARCHAR(36) NOT NULL,
        created_at DATETIME2 NOT NULL,
        content_hash VARCHAR(80) NOT NULL,
        CONSTRAINT PK_position_versions PRIMARY KEY (id),
        CONSTRAINT UQ_pv_position_version UNIQUE (position_id, version),
        CONSTRAINT FK_pv_position FOREIGN KEY (position_id) REFERENCES positions(id),
        CONSTRAINT FK_pv_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_pv_version CHECK (version >= 1)
    );
END
GO

IF OBJECT_ID('position_versions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pv_position_current'
          AND object_id = OBJECT_ID('position_versions')
   )
    CREATE UNIQUE INDEX IX_pv_position_current
        ON position_versions (position_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('position_versions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pv_aisle_asset'
          AND object_id = OBJECT_ID('position_versions')
   )
    CREATE INDEX IX_pv_aisle_asset
        ON position_versions (aisle_id, asset_id);
GO

IF OBJECT_ID('aisle_revisions', 'U') IS NULL
BEGIN
    CREATE TABLE aisle_revisions (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        base_finalization_id VARCHAR(36) NOT NULL,
        new_finalization_id VARCHAR(36) NULL,
        revision_type VARCHAR(40) NOT NULL,
        status VARCHAR(32) NOT NULL,
        reason NVARCHAR(500) NOT NULL,
        requested_by VARCHAR(36) NOT NULL,
        requested_at DATETIME2 NOT NULL,
        started_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        canceled_at DATETIME2 NULL,
        failed_at DATETIME2 NULL,
        failure_code VARCHAR(64) NULL,
        failure_message NVARCHAR(500) NULL,
        apply_id VARCHAR(36) NULL,
        snapshot_json NVARCHAR(MAX) NOT NULL,
        content_hash VARCHAR(80) NOT NULL,
        row_version INT NOT NULL CONSTRAINT DF_ar_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aisle_revisions PRIMARY KEY (id),
        CONSTRAINT FK_ar_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_ar_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_ar_revision_type CHECK (
            revision_type IN (
                'MANUAL_CORRECTION',
                'SERVER_PROPOSAL_ADOPTION',
                'ROLLBACK',
                'EXCLUSION_CHANGE',
                'REOPEN_AND_EDIT'
            )
        ),
        CONSTRAINT CK_ar_status CHECK (
            status IN (
                'DRAFT',
                'OPEN',
                'IN_REVIEW',
                'READY_TO_APPLY',
                'APPLYING',
                'COMPLETED',
                'CANCELED',
                'FAILED',
                'CONFLICTED'
            )
        )
    );
END
GO

IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ar_aisle_status'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE INDEX IX_ar_aisle_status
        ON aisle_revisions (aisle_id, status);
GO

IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ar_aisle_open'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE UNIQUE INDEX IX_ar_aisle_open
        ON aisle_revisions (aisle_id)
        WHERE status IN ('DRAFT', 'OPEN', 'IN_REVIEW', 'READY_TO_APPLY', 'APPLYING');
GO

IF OBJECT_ID('aisle_revision_items', 'U') IS NULL
BEGIN
    CREATE TABLE aisle_revision_items (
        id VARCHAR(36) NOT NULL,
        revision_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        base_result_id VARCHAR(36) NULL,
        base_position_id VARCHAR(36) NULL,
        proposed_internal_code VARCHAR(128) NULL,
        proposed_quantity INT NULL,
        proposed_exclusion_state VARCHAR(16) NULL,
        proposal_source VARCHAR(40) NOT NULL,
        proposal_reference_id VARCHAR(36) NULL,
        change_reason NVARCHAR(500) NULL,
        item_status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_ari PRIMARY KEY (id),
        CONSTRAINT UQ_ari_revision_asset UNIQUE (revision_id, asset_id),
        CONSTRAINT FK_ari_revision FOREIGN KEY (revision_id) REFERENCES aisle_revisions(id),
        CONSTRAINT CK_ari_proposal_source CHECK (
            proposal_source IN (
                'MANUAL',
                'SERVER_REPROCESS_PROPOSAL',
                'ROLLBACK_SOURCE',
                'EXCLUSION_CHANGE',
                'UNCHANGED'
            )
        ),
        CONSTRAINT CK_ari_item_status CHECK (
            item_status IN (
                'UNCHANGED',
                'MODIFIED',
                'EXCLUDED',
                'RESTORED',
                'ADOPT_REMOTE',
                'ROLLED_BACK',
                'CONFLICTED'
            )
        ),
        CONSTRAINT CK_ari_exclusion_state CHECK (
            proposed_exclusion_state IS NULL
            OR proposed_exclusion_state IN ('EXCLUDE', 'RESTORE', 'KEEP')
        )
    );
END
GO

IF OBJECT_ID('aisle_revision_items', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ari_revision'
          AND object_id = OBJECT_ID('aisle_revision_items')
   )
    CREATE INDEX IX_ari_revision
        ON aisle_revision_items (revision_id);
GO

IF OBJECT_ID('aisle_revision_locks', 'U') IS NULL
BEGIN
    CREATE TABLE aisle_revision_locks (
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        owner_token VARCHAR(64) NOT NULL,
        lease_expires_at DATETIME2 NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aisle_revision_locks PRIMARY KEY (aisle_id)
    );
END
GO
GO

-- ----- folded from 0070_aisle_revision_corrections.sql -----
-- Phase 8 corrections: apply content hash, position CAS columns, uniqueness constraints.
-- Additive / idempotent. Requires 0069_aisle_revisions_phase8.
-- Formal rollback (dev/test only):
--   ALTER TABLE aisle_revisions DROP COLUMN apply_content_hash;
--   ALTER TABLE aisle_revision_items DROP COLUMN base_position_version_id;
--   ALTER TABLE aisle_revision_items DROP COLUMN base_position_row_version;
--   DROP INDEX IF EXISTS UQ_ar_apply_id ON aisle_revisions;
--   DROP INDEX IF EXISTS IX_ar_inventory_status ON aisle_revisions;
--   DROP INDEX IF EXISTS IX_ar_new_finalization ON aisle_revisions;
--   DROP INDEX IF EXISTS IX_pv_revision ON position_versions;

IF COL_LENGTH('aisle_revisions', 'apply_content_hash') IS NULL
BEGIN
    ALTER TABLE aisle_revisions ADD apply_content_hash VARCHAR(80) NULL;
END
GO

IF COL_LENGTH('aisle_revision_items', 'base_position_version_id') IS NULL
BEGIN
    ALTER TABLE aisle_revision_items ADD base_position_version_id VARCHAR(36) NULL;
END
GO

IF COL_LENGTH('aisle_revision_items', 'base_position_row_version') IS NULL
BEGIN
    ALTER TABLE aisle_revision_items ADD base_position_row_version INT NULL;
END
GO

-- Unique apply_id when present (idempotent retries share the same id).
IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_ar_apply_id'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE UNIQUE INDEX UQ_ar_apply_id
        ON aisle_revisions (apply_id)
        WHERE apply_id IS NOT NULL;
GO

-- One current exclusion per asset (Phase 6 table; reinforce if missing).
IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_aaea_current_asset'
          AND object_id = OBJECT_ID('authoritative_aisle_excluded_assets')
   )
    CREATE UNIQUE INDEX UQ_aaea_current_asset
        ON authoritative_aisle_excluded_assets (aisle_id, asset_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('aisle_revision_items', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ari_revision_asset'
          AND object_id = OBJECT_ID('aisle_revision_items')
   )
    CREATE INDEX IX_ari_revision_asset
        ON aisle_revision_items (revision_id, asset_id);
GO

-- Inventory-wide revision listings (0069 only indexed by aisle).
IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ar_inventory_status'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE INDEX IX_ar_inventory_status
        ON aisle_revisions (inventory_id, status);
GO

-- Trace a published finalization back to the revision that created it.
IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ar_new_finalization'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE INDEX IX_ar_new_finalization
        ON aisle_revisions (new_finalization_id)
        WHERE new_finalization_id IS NOT NULL;
GO

-- Audit every position version a revision produced.
IF OBJECT_ID('position_versions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pv_revision'
          AND object_id = OBJECT_ID('position_versions')
   )
    CREATE INDEX IX_pv_revision
        ON position_versions (revision_id)
        WHERE revision_id IS NOT NULL;
GO
GO

-- ----- folded from 0073_inventory_jobs_retry_of_unique.sql -----
/*
  0073_inventory_jobs_retry_of_unique.sql

  Phase 5 corrections — at most one child job per retry_of_job_id (idempotent recovery).

  Preflight / rollback / reapply: see 0073_README.md in this directory.
  Rollback: DROP INDEX IF EXISTS UX_inventory_jobs_retry_of_job_id ON dbo.inventory_jobs;
*/

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'UX_inventory_jobs_retry_of_job_id'
      AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
)
BEGIN
    -- Pre-check: duplicate parents would block index creation.
    IF EXISTS (
        SELECT retry_of_job_id
        FROM dbo.inventory_jobs
        WHERE retry_of_job_id IS NOT NULL
        GROUP BY retry_of_job_id
        HAVING COUNT(*) > 1
    )
    BEGIN
        RAISERROR(
            'Cannot create UX_inventory_jobs_retry_of_job_id: duplicate retry_of_job_id rows exist',
            16,
            1
        );
        RETURN;
    END;

    CREATE UNIQUE NONCLUSTERED INDEX UX_inventory_jobs_retry_of_job_id
        ON dbo.inventory_jobs(retry_of_job_id)
        WHERE retry_of_job_id IS NOT NULL;
END;
GO
GO

-- ----- folded from 0077_aisle_location_label_artifacts.sql -----
/*
  0077_aisle_location_label_artifacts.sql

  Phase 2 — durable rendered positioning label artifacts (PDF/PNG).

  Apply: db_migrate apply / service.apply_pending (UP only).
  Rollback (manual): 0077_aisle_location_label_artifacts.down.sql
*/

IF OBJECT_ID(N'dbo.aisle_location_label_artifacts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.aisle_location_label_artifacts (
        id VARCHAR(36) NOT NULL CONSTRAINT PK_aisle_location_label_artifacts PRIMARY KEY,
        label_id VARCHAR(36) NOT NULL,
        format VARCHAR(16) NOT NULL,
        preset VARCHAR(32) NOT NULL,
        template_version INT NOT NULL,
        marker_version INT NOT NULL,
        storage_provider VARCHAR(32) NOT NULL,
        storage_bucket VARCHAR(255) NULL,
        storage_key VARCHAR(512) NOT NULL,
        content_type VARCHAR(128) NOT NULL,
        file_size_bytes BIGINT NOT NULL,
        artifact_hash VARCHAR(64) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_aisle_location_label_artifacts_label
            FOREIGN KEY (label_id) REFERENCES dbo.aisle_location_labels(id),
        CONSTRAINT CK_aisle_location_label_artifacts_format
            CHECK (format IN (N'PDF', N'PNG')),
        CONSTRAINT CK_aisle_location_label_artifacts_sizes
            CHECK (template_version >= 1 AND marker_version >= 1 AND file_size_bytes >= 0)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_location_label_artifacts_identity'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_location_label_artifacts_identity
        ON dbo.aisle_location_label_artifacts(
            label_id, format, preset, template_version, marker_version
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_aisle_location_label_artifacts_label_created'
      AND object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
)
    CREATE NONCLUSTERED INDEX IX_aisle_location_label_artifacts_label_created
        ON dbo.aisle_location_label_artifacts(label_id, created_at DESC);
GO
GO

-- ----- folded from 0078_phase2_positioning_label_hardening.sql -----
/*
  0078_phase2_positioning_label_hardening.sql

  Phase 2 corrections:
  - aisle_locations.public_identifier (payload position_id)
  - aisle_location_labels.replaced_at
  - artifact lifecycle status + failure fields
  - nullable storage fields for PENDING reservation

  Rollback: 0078_phase2_positioning_label_hardening.down.sql
*/

-- ---------------------------------------------------------------------------
-- aisle_locations.public_identifier
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations') AND name = N'public_identifier'
)
    ALTER TABLE dbo.aisle_locations ADD public_identifier VARCHAR(64) NULL;
GO

-- Backfill existing rows (stable public ids distinct from internal UUID).
UPDATE dbo.aisle_locations
SET public_identifier = CONCAT(N'loc_', REPLACE(CONVERT(VARCHAR(36), id), N'-', N''))
WHERE public_identifier IS NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations') AND name = N'public_identifier'
)
AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_locations')
      AND name = N'public_identifier'
      AND is_nullable = 0
)
BEGIN
    ALTER TABLE dbo.aisle_locations ALTER COLUMN public_identifier VARCHAR(64) NOT NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_aisle_locations_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.aisle_locations')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_aisle_locations_public_identifier
        ON dbo.aisle_locations(public_identifier);
GO

-- ---------------------------------------------------------------------------
-- aisle_location_labels.replaced_at
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_labels') AND name = N'replaced_at'
)
    ALTER TABLE dbo.aisle_location_labels ADD replaced_at DATETIME2 NULL;
GO

-- ---------------------------------------------------------------------------
-- artifact lifecycle
-- ---------------------------------------------------------------------------
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'status'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD status VARCHAR(16) NOT NULL
        CONSTRAINT DF_aisle_location_label_artifacts_status DEFAULT (N'READY');
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'failure_code'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD failure_code VARCHAR(64) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'failure_detail'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD failure_detail NVARCHAR(500) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'updated_at'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD updated_at DATETIME2 NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts') AND name = N'render_owner'
)
    ALTER TABLE dbo.aisle_location_label_artifacts ADD render_owner VARCHAR(64) NULL;
GO

UPDATE dbo.aisle_location_label_artifacts
SET updated_at = created_at
WHERE updated_at IS NULL;
GO

-- Allow PENDING rows before storage upload completes.
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_location_label_artifacts')
      AND name = N'storage_key'
      AND is_nullable = 0
)
    ALTER TABLE dbo.aisle_location_label_artifacts ALTER COLUMN storage_key VARCHAR(512) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_aisle_location_label_artifacts_status'
)
    ALTER TABLE dbo.aisle_location_label_artifacts
        ADD CONSTRAINT CK_aisle_location_label_artifacts_status
        CHECK (status IN (N'PENDING', N'RENDERING', N'READY', N'FAILED'));
GO
GO

-- ----- folded from 0079_client_position_labels.sql -----
/*
  0079_client_position_labels.sql

  Simplify positioning labels to client scope:
  - New dbo.client_position_labels (no inventory/aisle ownership)
  - New dbo.client_position_label_artifacts
  - Migrate labels from aisle_location_labels when present
  - Preserve public_identifier when possible

  Rollback: 0079_client_position_labels.down.sql
*/

-- ---------------------------------------------------------------------------
-- client_position_labels
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.client_position_labels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_position_labels (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        public_identifier VARCHAR(64) NOT NULL,
        name NVARCHAR(200) NOT NULL,
        normalized_name NVARCHAR(200) NOT NULL,
        description NVARCHAR(1000) NULL,
        status VARCHAR(32) NOT NULL
            CONSTRAINT DF_client_position_labels_status DEFAULT ('ACTIVE'),
        payload_version INT NOT NULL
            CONSTRAINT DF_client_position_labels_payload_version DEFAULT (1),
        canonical_payload NVARCHAR(MAX) NOT NULL,
        payload_hash VARCHAR(128) NULL,
        signature NVARCHAR(128) NULL,
        signature_algorithm VARCHAR(32) NULL,
        signature_key_version INT NULL,
        signature_status VARCHAR(32) NOT NULL
            CONSTRAINT DF_client_position_labels_sig_status DEFAULT ('UNSIGNED'),
        created_by VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        invalidated_at DATETIME2 NULL,
        invalidation_reason NVARCHAR(512) NULL,
        idempotency_key NVARCHAR(128) NULL,
        idempotency_request_hash VARCHAR(64) NULL,
        CONSTRAINT PK_client_position_labels PRIMARY KEY (id),
        CONSTRAINT FK_client_position_labels_client
            FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT CK_client_position_labels_status CHECK (status IN ('ACTIVE', 'INVALIDATED')),
        CONSTRAINT CK_client_position_labels_signature_status CHECK (
            signature_status IN ('NOT_IMPLEMENTED', 'UNSIGNED', 'SIGNED')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_labels_public_identifier
        ON dbo.client_position_labels(public_identifier);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_client_position_labels_client_status'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE NONCLUSTERED INDEX IX_client_position_labels_client_status
        ON dbo.client_position_labels(client_id, status, created_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_client_idempotency'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_labels_client_idempotency
        ON dbo.client_position_labels(client_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
GO

-- ---------------------------------------------------------------------------
-- client_position_label_artifacts
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.client_position_label_artifacts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_position_label_artifacts (
        id VARCHAR(36) NOT NULL,
        label_id VARCHAR(36) NOT NULL,
        format VARCHAR(8) NOT NULL,
        preset VARCHAR(32) NOT NULL,
        template_version INT NOT NULL,
        marker_version INT NOT NULL,
        content_type VARCHAR(64) NOT NULL,
        file_size_bytes BIGINT NOT NULL,
        artifact_hash VARCHAR(64) NOT NULL,
        storage_key NVARCHAR(512) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_client_position_label_artifacts PRIMARY KEY (id),
        CONSTRAINT CK_client_position_label_artifacts_format CHECK (format IN ('PDF', 'PNG')),
        CONSTRAINT FK_client_position_label_artifacts_label
            FOREIGN KEY (label_id) REFERENCES dbo.client_position_labels(id)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_label_artifacts_identity'
      AND object_id = OBJECT_ID(N'dbo.client_position_label_artifacts')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_label_artifacts_identity
        ON dbo.client_position_label_artifacts(label_id, format, preset, template_version, marker_version);
GO

-- ---------------------------------------------------------------------------
-- Data migrate: aisle_location_labels → client_position_labels
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.aisle_location_labels', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.aisle_locations', N'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.client_position_labels (
        id, client_id, public_identifier, name, normalized_name, description,
        status, payload_version, canonical_payload, payload_hash,
        signature, signature_algorithm, signature_key_version, signature_status,
        created_by, created_at, updated_at, invalidated_at, invalidation_reason,
        idempotency_key, idempotency_request_hash
    )
    SELECT
        l.id,
        l.client_id,
        l.public_identifier,
        COALESCE(NULLIF(LTRIM(RTRIM(loc.display_name)), N''), loc.code),
        UPPER(COALESCE(NULLIF(LTRIM(RTRIM(loc.normalized_code)), N''), loc.code)),
        loc.description,
        CASE WHEN l.status = N'INVALIDATED' THEN N'INVALIDATED' ELSE N'ACTIVE' END,
        l.payload_version,
        CASE
            WHEN ISJSON(CONVERT(NVARCHAR(MAX), l.payload_json)) = 1
                THEN CONVERT(NVARCHAR(MAX), l.payload_json)
            ELSE N'{"type":"DINAMIC_POSITION","version":1,"label_id":"' + l.public_identifier + N'"}'
        END,
        l.payload_hash,
        CASE
            WHEN ISJSON(CONVERT(NVARCHAR(MAX), l.payload_json)) = 1
                THEN JSON_VALUE(CONVERT(NVARCHAR(MAX), l.payload_json), '$.signature')
            ELSE NULL
        END,
        CASE WHEN l.signature_status = N'SIGNED' THEN N'HMAC-SHA256' ELSE NULL END,
        CASE
            WHEN ISJSON(CONVERT(NVARCHAR(MAX), l.payload_json)) = 1
                THEN TRY_CONVERT(INT, JSON_VALUE(CONVERT(NVARCHAR(MAX), l.payload_json), '$.key_version'))
            ELSE NULL
        END,
        CASE
            WHEN l.signature_status IN (N'SIGNED', N'UNSIGNED', N'NOT_IMPLEMENTED')
                THEN l.signature_status
            ELSE N'UNSIGNED'
        END,
        l.generated_by,
        l.generated_at,
        COALESCE(l.generated_at, SYSUTCDATETIME()),
        l.invalidated_at,
        l.invalidation_reason,
        l.idempotency_key,
        l.idempotency_request_hash
    FROM dbo.aisle_location_labels l
    INNER JOIN dbo.aisle_locations loc ON loc.id = l.location_id
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.client_position_labels c WHERE c.id = l.id
    )
    AND NOT EXISTS (
        SELECT 1 FROM dbo.client_position_labels c2
        WHERE c2.public_identifier = l.public_identifier
    );
END
GO

IF OBJECT_ID(N'dbo.aisle_location_label_artifacts', N'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.client_position_label_artifacts (
        id, label_id, format, preset, template_version, marker_version,
        content_type, file_size_bytes, artifact_hash, storage_key, created_at
    )
    SELECT
        a.id, a.label_id, a.format, a.preset, a.template_version, a.marker_version,
        a.content_type, a.file_size_bytes, a.artifact_hash,
        COALESCE(a.storage_key, N'migrated-empty'), a.created_at
    FROM dbo.aisle_location_label_artifacts a
    INNER JOIN dbo.client_position_labels c ON c.id = a.label_id
    WHERE a.storage_key IS NOT NULL
      AND LTRIM(RTRIM(a.storage_key)) <> N''
      AND NOT EXISTS (
          SELECT 1 FROM dbo.client_position_label_artifacts x WHERE x.id = a.id
      );
END
GO
GO

-- ----- folded from 0080_image_position_label_detections.sql -----
/*
  0080_image_position_label_detections.sql

  Phase 3 — persist per-image DINAMIC_POSITION detections (no product binding).

  Rollback: 0080_image_position_label_detections.down.sql
*/

IF OBJECT_ID(N'dbo.image_position_label_detections', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.image_position_label_detections (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        client_image_id VARCHAR(64) NULL,
        ordered_capture_session_id VARCHAR(36) NULL,
        sequence_number INT NULL,
        position_label_id VARCHAR(36) NULL,
        public_identifier VARCHAR(64) NULL,
        position_name_snapshot NVARCHAR(200) NULL,
        payload_version INT NULL,
        signature_status VARCHAR(32) NOT NULL,
        detection_status VARCHAR(64) NOT NULL,
        confidence FLOAT NULL,
        bounding_box_json NVARCHAR(MAX) NULL,
        rotation_degrees FLOAT NULL,
        raw_payload_hash VARCHAR(128) NULL,
        detector_name VARCHAR(64) NOT NULL,
        detector_version VARCHAR(64) NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_image_position_label_detections PRIMARY KEY (id),
        CONSTRAINT FK_ipld_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_ipld_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_ipld_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_ipld_asset FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id),
        CONSTRAINT FK_ipld_label FOREIGN KEY (position_label_id) REFERENCES dbo.client_position_labels(id),
        CONSTRAINT CK_ipld_signature_status CHECK (
            signature_status IN ('VALID', 'INVALID', 'MISSING', 'SKIPPED', 'UNKNOWN_KEY')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ipld_asset_detector_hash_status
        ON dbo.image_position_label_detections(
            source_asset_id,
            detector_version,
            detection_status,
            raw_payload_hash
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_job'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_job
        ON dbo.image_position_label_detections(job_id, sequence_number, created_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_asset'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_asset
        ON dbo.image_position_label_detections(source_asset_id, detection_status);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_label'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_label
        ON dbo.image_position_label_detections(position_label_id)
        WHERE position_label_id IS NOT NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ipld_client_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE NONCLUSTERED INDEX IX_ipld_client_status
        ON dbo.image_position_label_detections(client_id, detection_status, created_at DESC);
GO
GO

-- ----- folded from 0081_image_position_label_detections_job_scope.sql -----
/*
  0081_image_position_label_detections_job_scope.sql

  Phase 3 corrections:
  - Job-scoped unique identity (preserve history across jobs)
  - detection_status CHECK
  - Drop pre-0081 asset-only unique index

  Rollback: 0081_image_position_label_detections_job_scope.down.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    DROP INDEX UQ_ipld_asset_detector_hash_status ON dbo.image_position_label_detections;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_job_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ipld_job_asset_detector_hash_status
        ON dbo.image_position_label_detections(
            job_id,
            source_asset_id,
            detector_version,
            detection_status,
            raw_payload_hash
        );
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_ipld_detection_status'
      AND parent_object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
BEGIN
    ALTER TABLE dbo.image_position_label_detections WITH NOCHECK
    ADD CONSTRAINT CK_ipld_detection_status CHECK (
        detection_status IN (
            'VALID',
            'INVALID_JSON',
            'INVALID_TYPE',
            'UNSUPPORTED_VERSION',
            'UNSUPPORTED_LEGACY_PAYLOAD',
            'MISSING_LABEL_ID',
            'MISSING_SIGNATURE',
            'INVALID_SIGNATURE',
            'UNKNOWN_KEY_VERSION',
            'SIGNATURE_VALIDATION_SKIPPED',
            'LABEL_NOT_FOUND',
            'LABEL_INVALIDATED',
            'CLIENT_MISMATCH',
            'DUPLICATE_POSITION_CODES',
            'AMBIGUOUS_POSITION_DETECTION',
            'PAYLOAD_TOO_LARGE',
            'DECODE_TIMEOUT',
            'DETECTION_FAILED',
            'DETECTION_CONTEXT_INVALID',
            'NO_LABEL',
            'FEATURE_DISABLED'
        )
    );
END
GO
GO

-- ----- folded from 0082_position_reconciliation.sql -----
/*
  0082_position_reconciliation.sql

  Phase 4 — durable sequential product-to-position reconciliation.
  Rollback: 0082_position_reconciliation.down.sql
*/

IF OBJECT_ID(N'dbo.position_reconciliations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.position_reconciliations (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        ordered_capture_session_id VARCHAR(36) NULL,
        reconciliation_name VARCHAR(100) NOT NULL,
        reconciliation_version VARCHAR(32) NOT NULL,
        input_fingerprint VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL,
        started_at DATETIME2 NOT NULL,
        completed_at DATETIME2 NULL,
        failure_code VARCHAR(64) NULL,
        attempt_count INT NOT NULL,
        assigned_count INT NOT NULL,
        unassigned_count INT NOT NULL,
        sequence_gap_count INT NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        is_active BIT NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        superseded_at DATETIME2 NULL,
        CONSTRAINT PK_position_reconciliations PRIMARY KEY (id),
        CONSTRAINT FK_position_reconciliations_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_position_reconciliations_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_position_reconciliations_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT CK_position_reconciliations_status CHECK (
            status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'STALE')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UQ_position_reconciliations_active_job'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_position_reconciliations_active_job
        ON dbo.position_reconciliations(job_id) WHERE is_active = 1;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_position_reconciliations_job'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_position_reconciliations_job
        ON dbo.position_reconciliations(job_id, created_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_position_reconciliations_status'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_position_reconciliations_status
        ON dbo.position_reconciliations(status, updated_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_position_reconciliations_version'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_position_reconciliations_version
        ON dbo.position_reconciliations(reconciliation_version, job_id);
GO

IF OBJECT_ID(N'dbo.product_position_assignments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_position_assignments (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        result_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        ordered_capture_session_id VARCHAR(36) NULL,
        sequence_number INT NULL,
        position_label_id VARCHAR(36) NULL,
        position_name_snapshot NVARCHAR(200) NULL,
        source_detection_id VARCHAR(36) NULL,
        assignment_status VARCHAR(64) NOT NULL,
        assignment_reason VARCHAR(128) NOT NULL,
        assignment_source VARCHAR(32) NULL,
        reconciliation_id VARCHAR(36) NOT NULL,
        reconciliation_version VARCHAR(32) NOT NULL,
        is_active BIT NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        superseded_at DATETIME2 NULL,
        CONSTRAINT PK_product_position_assignments PRIMARY KEY (id),
        CONSTRAINT FK_ppa_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_ppa_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_ppa_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_ppa_result FOREIGN KEY (result_id) REFERENCES dbo.product_records(id),
        CONSTRAINT FK_ppa_asset FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id),
        CONSTRAINT FK_ppa_label FOREIGN KEY (position_label_id) REFERENCES dbo.client_position_labels(id),
        CONSTRAINT FK_ppa_detection FOREIGN KEY (source_detection_id) REFERENCES dbo.image_position_label_detections(id),
        CONSTRAINT FK_ppa_reconciliation FOREIGN KEY (reconciliation_id) REFERENCES dbo.position_reconciliations(id)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UQ_ppa_active_job_result'
      AND object_id = OBJECT_ID(N'dbo.product_position_assignments')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ppa_active_job_result
        ON dbo.product_position_assignments(job_id, result_id) WHERE is_active = 1;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_job' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_job ON dbo.product_position_assignments(job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_result' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_result ON dbo.product_position_assignments(result_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_position_label' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_position_label ON dbo.product_position_assignments(position_label_id) WHERE position_label_id IS NOT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_assignment_status' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_assignment_status ON dbo.product_position_assignments(assignment_status, job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_reconciliation_version' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_reconciliation_version ON dbo.product_position_assignments(reconciliation_version, job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_is_active' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_is_active ON dbo.product_position_assignments(is_active, job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_sequence_number' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_sequence_number ON dbo.product_position_assignments(job_id, sequence_number);
GO
GO

-- ----- folded from 0083_position_reconciliation_hardening.sql -----
/*
  0083_position_reconciliation_hardening.sql

  Enforce valid and internally consistent Phase 4 assignment rows.
*/

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_assignment_status CHECK (
    assignment_status IN (
        'ASSIGNED_AUTOMATIC',
        'UNASSIGNED_NO_PREVIOUS_POSITION',
        'UNASSIGNED_AFTER_AMBIGUOUS_POSITION',
        'UNASSIGNED_INVALID_POSITION',
        'UNASSIGNED_UNORDERED_ASSET',
        'SKIPPED_NO_ITEM_RESULT'
    )
);
GO

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_assignment_source CHECK (
    assignment_source IS NULL OR assignment_source = 'AUTOMATIC'
);
GO

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_automatic_evidence CHECK (
    assignment_status <> 'ASSIGNED_AUTOMATIC'
    OR (position_label_id IS NOT NULL AND source_detection_id IS NOT NULL)
);
GO

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_unassigned_position_null CHECK (
    assignment_status = 'ASSIGNED_AUTOMATIC' OR position_label_id IS NULL
);
GO
GO

-- ----- folded from 0084_manual_product_position_overrides.sql -----
/*
  Phase 6: immutable manual product-position override revisions.
  Automatic assignments and reconciliations remain unchanged.
*/
IF OBJECT_ID(N'dbo.manual_product_position_overrides', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.manual_product_position_overrides (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        result_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NULL,
        automatic_assignment_id VARCHAR(36) NULL,
        automatic_reconciliation_id VARCHAR(36) NULL,
        previous_effective_position_label_id VARCHAR(36) NULL,
        new_position_label_id VARCHAR(36) NULL,
        new_position_name_snapshot NVARCHAR(200) NULL,
        override_action VARCHAR(32) NOT NULL,
        reason_code VARCHAR(64) NOT NULL,
        reason_text NVARCHAR(1000) NULL,
        -- External JWT subject: deliberately no FK; application validates non-empty value.
        created_by_user_id VARCHAR(128) NOT NULL,
        created_by_role VARCHAR(64) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        version INT NOT NULL,
        is_active BIT NOT NULL,
        superseded_override_id VARCHAR(36) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        deactivated_at DATETIME2 NULL,
        CONSTRAINT PK_manual_product_position_overrides PRIMARY KEY (id),
        CONSTRAINT FK_mppo_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_mppo_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_mppo_aisle FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id),
        CONSTRAINT FK_mppo_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_mppo_result FOREIGN KEY (result_id) REFERENCES dbo.product_records(id),
        CONSTRAINT FK_mppo_asset FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id),
        CONSTRAINT FK_mppo_auto_assignment FOREIGN KEY (automatic_assignment_id)
            REFERENCES dbo.product_position_assignments(id),
        CONSTRAINT FK_mppo_auto_reconciliation FOREIGN KEY (automatic_reconciliation_id)
            REFERENCES dbo.position_reconciliations(id),
        CONSTRAINT FK_mppo_previous_label FOREIGN KEY (previous_effective_position_label_id)
            REFERENCES dbo.client_position_labels(id),
        CONSTRAINT FK_mppo_new_label FOREIGN KEY (new_position_label_id)
            REFERENCES dbo.client_position_labels(id),
        CONSTRAINT FK_mppo_superseded FOREIGN KEY (superseded_override_id)
            REFERENCES dbo.manual_product_position_overrides(id),
        CONSTRAINT CK_mppo_version CHECK (version > 0),
        CONSTRAINT CK_mppo_action CHECK (
            override_action IN (
                'ASSIGN_POSITION', 'CHANGE_POSITION', 'REMOVE_POSITION', 'RESTORE_AUTOMATIC'
            )
        ),
        CONSTRAINT CK_mppo_reason CHECK (
            reason_code IN (
                'WRONG_POSITION_DETECTED', 'PRODUCT_MOVED', 'SEQUENCE_ERROR',
                'POSITION_LABEL_NOT_VISIBLE', 'POSITION_LABEL_INVALID', 'AMBIGUOUS_IMAGE',
                'MISSING_POSITION_LABEL', 'OPERATOR_VERIFICATION', 'DATA_CORRECTION', 'OTHER'
            )
        ),
        CONSTRAINT CK_mppo_action_position CHECK (
            (override_action IN ('ASSIGN_POSITION', 'CHANGE_POSITION')
                AND new_position_label_id IS NOT NULL)
            OR (override_action IN ('REMOVE_POSITION', 'RESTORE_AUTOMATIC')
                AND new_position_label_id IS NULL)
        ),
        CONSTRAINT CK_mppo_restore_inactive CHECK (
            override_action <> 'RESTORE_AUTOMATIC' OR is_active = 0
        ),
        CONSTRAINT CK_mppo_other_reason_text CHECK (
            reason_code <> 'OTHER' OR LEN(LTRIM(RTRIM(ISNULL(reason_text, '')))) > 0
        )
    );
END
GO

IF OBJECT_ID(N'dbo.product_position_effective_versions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_position_effective_versions (
        job_id VARCHAR(36) NOT NULL,
        result_id VARCHAR(36) NOT NULL,
        version INT NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_product_position_effective_versions PRIMARY KEY (job_id, result_id),
        CONSTRAINT FK_ppev_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_ppev_result FOREIGN KEY (result_id) REFERENCES dbo.product_records(id),
        CONSTRAINT CK_ppev_version CHECK (version > 0)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_manual_position_override_active'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_position_override_active
        ON dbo.manual_product_position_overrides(job_id, result_id) WHERE is_active = 1;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_manual_position_override_idempotency'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_position_override_idempotency
        ON dbo.manual_product_position_overrides(client_id, idempotency_key);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_mppo_job_result_version'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_mppo_job_result_version
        ON dbo.manual_product_position_overrides(job_id, result_id, version);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mppo_job_result'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE NONCLUSTERED INDEX IX_mppo_job_result
        ON dbo.manual_product_position_overrides(job_id, result_id, version DESC);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mppo_new_label'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE NONCLUSTERED INDEX IX_mppo_new_label
        ON dbo.manual_product_position_overrides(new_position_label_id)
        WHERE new_position_label_id IS NOT NULL;
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mppo_created_by'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE NONCLUSTERED INDEX IX_mppo_created_by
        ON dbo.manual_product_position_overrides(created_by_user_id);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mppo_created_at'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE NONCLUSTERED INDEX IX_mppo_created_at
        ON dbo.manual_product_position_overrides(created_at);
GO
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_mppo_active_reason'
      AND object_id = OBJECT_ID(N'dbo.manual_product_position_overrides')
)
    CREATE NONCLUSTERED INDEX IX_mppo_active_reason
        ON dbo.manual_product_position_overrides(is_active, reason_code);
GO
GO

-- ----- folded from 0085_ipld_legacy_unsigned_detection_status.sql -----
/*
  0085_ipld_legacy_unsigned_detection_status.sql

  Allow LEGACY_UNSIGNED_REQUIRES_REVIEW in image_position_label_detections.detection_status.

  Domain/enum already emits this status when a stored unsigned position label matches the
  QR payload. Migration 0081 CHECK omitted it, so persistence raised IntegrityError and
  position detections were dropped — product↔position reconciliation then stayed unassigned.

  Rollback: 0085_ipld_legacy_unsigned_detection_status.down.sql
*/

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_ipld_detection_status'
      AND parent_object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    ALTER TABLE dbo.image_position_label_detections DROP CONSTRAINT CK_ipld_detection_status;
GO

ALTER TABLE dbo.image_position_label_detections WITH NOCHECK
ADD CONSTRAINT CK_ipld_detection_status CHECK (
    detection_status IN (
        'VALID',
        'INVALID_JSON',
        'INVALID_TYPE',
        'UNSUPPORTED_VERSION',
        'UNSUPPORTED_LEGACY_PAYLOAD',
        'MISSING_LABEL_ID',
        'MISSING_SIGNATURE',
        'INVALID_SIGNATURE',
        'UNKNOWN_KEY_VERSION',
        'SIGNATURE_VALIDATION_SKIPPED',
        'LABEL_NOT_FOUND',
        'LABEL_INVALIDATED',
        'CLIENT_MISMATCH',
        'DUPLICATE_POSITION_CODES',
        'AMBIGUOUS_POSITION_DETECTION',
        'PAYLOAD_TOO_LARGE',
        'DECODE_TIMEOUT',
        'DETECTION_FAILED',
        'DETECTION_CONTEXT_INVALID',
        'NO_LABEL',
        'FEATURE_DISABLED',
        'LEGACY_UNSIGNED_REQUIRES_REVIEW'
    )
);
GO
GO

-- ----- folded from 0086_local_csv_imports.sql -----
/*
  Local CSV import staging + productive results (ingestion channel vs detection source).
  Version 0086 — replaces the misnumbered WIP formerly named 0074_local_csv_imports
  (which collided with 0074_ordered_capture_sessions_and_positioning_foundation).
  Does not create source_assets or fake photos.

  Column types match dbo.inventories(id) / dbo.aisles(id): VARCHAR(36).
*/

IF OBJECT_ID(N'dbo.local_csv_imports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_csv_imports (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        export_id NVARCHAR(255) NOT NULL,
        schema_version NVARCHAR(16) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
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
        confirmed_by_user_id VARCHAR(128) NULL,
        csv_company_id NVARCHAR(255) NULL,
        csv_client_id NVARCHAR(255) NULL,
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
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        import_id VARCHAR(36) NOT NULL,
        row_number INT NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
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
        -- Detection provenance from CSV column `source` (LOCAL_CODE_SCAN, …).
        detection_source NVARCHAR(64) NOT NULL,
        -- Server-assigned channel; never taken from the client as authoritative.
        ingestion_source NVARCHAR(64) NOT NULL
            CONSTRAINT DF_local_csv_import_rows_ingestion
            DEFAULT N'LOCAL_CSV_IMPORT',
        requires_review BIT NOT NULL,
        error_code NVARCHAR(255) NULL,
        notes NVARCHAR(2000) NULL,
        status NVARCHAR(32) NOT NULL,
        validation_errors_json NVARCHAR(MAX) NOT NULL,
        validation_warnings_json NVARCHAR(MAX) NOT NULL,
        productive_result_id VARCHAR(36) NULL,
        CONSTRAINT FK_local_csv_import_rows_import
            FOREIGN KEY (import_id) REFERENCES dbo.local_csv_imports(id) ON DELETE CASCADE,
        CONSTRAINT UX_local_csv_import_rows_number UNIQUE (import_id, row_number),
        CONSTRAINT CK_local_csv_import_rows_detection_source
            CHECK (detection_source IN (
                N'LOCAL_PENDING',
                N'LOCAL_CODE_SCAN',
                N'LOCAL_MANUAL',
                N'LOCAL_MANUAL_CORRECTION',
                N'LOCAL_POSITION_LABEL',
                N'LOCAL_CODE_SCAN_SHADOW'
            )),
        CONSTRAINT CK_local_csv_import_rows_ingestion_source
            CHECK (ingestion_source = N'LOCAL_CSV_IMPORT'),
        CONSTRAINT CK_local_csv_import_rows_status
            CHECK (status IN ('PREVIEW_VALID', 'REJECTED', 'IMPORTED', 'DUPLICATE', 'REQUIRES_REVIEW'))
    );

    CREATE INDEX IX_local_csv_import_rows_secondary
        ON dbo.local_csv_import_rows(capture_session_id, capture_photo_id, status);

    CREATE UNIQUE INDEX UX_local_csv_import_rows_imported_secondary
        ON dbo.local_csv_import_rows(capture_session_id, capture_photo_id)
        WHERE status = 'IMPORTED';
END;
GO

IF OBJECT_ID(N'dbo.local_csv_productive_results', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_csv_productive_results (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        import_id VARCHAR(36) NOT NULL,
        import_row_id VARCHAR(36) NOT NULL,
        capture_session_id NVARCHAR(255) NOT NULL,
        capture_photo_id NVARCHAR(255) NOT NULL,
        client_file_id NVARCHAR(255) NOT NULL,
        capture_order INT NULL,
        position_code NVARCHAR(255) NULL,
        internal_code NVARCHAR(255) NULL,
        quantity INT NULL,
        quantity_status NVARCHAR(64) NOT NULL,
        detection_status NVARCHAR(64) NOT NULL,
        detection_source NVARCHAR(64) NOT NULL,
        ingestion_source NVARCHAR(64) NOT NULL,
        requires_review BIT NOT NULL,
        has_image_evidence BIT NOT NULL
            CONSTRAINT DF_local_csv_productive_has_image DEFAULT 0,
        confirmed_by_user_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_local_csv_productive_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_local_csv_productive_import
            FOREIGN KEY (import_id) REFERENCES dbo.local_csv_imports(id),
        CONSTRAINT FK_local_csv_productive_row
            FOREIGN KEY (import_row_id) REFERENCES dbo.local_csv_import_rows(id),
        CONSTRAINT UX_local_csv_productive_import_row UNIQUE (import_row_id),
        CONSTRAINT UX_local_csv_productive_secondary UNIQUE (capture_session_id, capture_photo_id),
        CONSTRAINT CK_local_csv_productive_ingestion
            CHECK (ingestion_source = N'LOCAL_CSV_IMPORT'),
        CONSTRAINT CK_local_csv_productive_no_fake_image
            CHECK (has_image_evidence = 0)
    );

    CREATE INDEX IX_local_csv_productive_inventory
        ON dbo.local_csv_productive_results(inventory_id, aisle_id);
END;
GO
GO

-- ----- folded from 0087_local_inventory_packages.sql -----
/*
  Local inventory ZIP package import + productive image evidence.
  Version 0087.

  - Relaxes CK_local_csv_productive_no_fake_image so package imports may set
    has_image_evidence=1 with source_asset_id.
  - Adds staging tables for package preview/confirm.
*/

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'source_asset_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD source_asset_id VARCHAR(36) NULL;
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_no_fake_image'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT CK_local_csv_productive_no_fake_image;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_image_evidence'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT CK_local_csv_productive_image_evidence
        CHECK (
            (has_image_evidence = 0 AND source_asset_id IS NULL)
            OR (has_image_evidence = 1 AND source_asset_id IS NOT NULL)
        );
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys
    WHERE name = N'FK_local_csv_productive_source_asset'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT FK_local_csv_productive_source_asset
        FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id);
END;
GO

IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_inventory_packages (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        export_id NVARCHAR(255) NOT NULL,
        csv_import_id VARCHAR(36) NOT NULL,
        package_kind NVARCHAR(64) NOT NULL,
        package_version INT NOT NULL,
        status NVARCHAR(32) NOT NULL,
        package_checksum_sha256 NVARCHAR(80) NULL,
        csv_checksum_sha256 NVARCHAR(80) NOT NULL,
        expected_photo_count INT NOT NULL,
        included_photo_count INT NOT NULL,
        aisle_id VARCHAR(36) NULL,
        capture_session_id NVARCHAR(255) NULL,
        freeze_id NVARCHAR(255) NULL,
        staging_dir NVARCHAR(1024) NOT NULL,
        confirmed_at DATETIME2 NULL,
        confirmed_by_user_id VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_local_inventory_packages_inventory
            FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_local_inventory_packages_csv_import
            FOREIGN KEY (csv_import_id) REFERENCES dbo.local_csv_imports(id),
        CONSTRAINT UX_local_inventory_packages_inventory_export
            UNIQUE (inventory_id, export_id),
        CONSTRAINT CK_local_inventory_packages_status
            CHECK (status IN ('PREVIEWED', 'CONFIRMED'))
    );
END;
GO

IF OBJECT_ID(N'dbo.local_inventory_package_photos', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.local_inventory_package_photos (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        package_id VARCHAR(36) NOT NULL,
        capture_photo_id NVARCHAR(255) NOT NULL,
        client_file_id NVARCHAR(255) NOT NULL,
        sequence_number INT NULL,
        file_name NVARCHAR(255) NOT NULL,
        mime_type NVARCHAR(128) NOT NULL,
        size_bytes INT NOT NULL,
        sha256 NVARCHAR(80) NOT NULL,
        width INT NULL,
        height INT NULL,
        asset_variant NVARCHAR(32) NOT NULL,
        staging_path NVARCHAR(1024) NOT NULL,
        source_asset_id VARCHAR(36) NULL,
        CONSTRAINT FK_local_inventory_package_photos_package
            FOREIGN KEY (package_id) REFERENCES dbo.local_inventory_packages(id) ON DELETE CASCADE,
        CONSTRAINT UX_local_inventory_package_photos_capture
            UNIQUE (package_id, capture_photo_id)
    );
END;
GO
GO

-- ----- folded from 0088_product_label_identity.sql -----
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
GO

-- ----- folded from 0089_product_label_identity_hardening.sql -----
/*
  0089_product_label_identity_hardening.sql

  Corrective constraints for D1 product labels (0088 already created tables).
  - Tighten issued quantity / label_id length
  - Document: no FK product_records.label_id → issued (legacy NULL; scan may precede sync)
  - Document: no FK on inventory_counted first_* ids (insert order: claim before product_record
    is created with preallocated UUID; claim row may outlive product on rollback races —
    claim and product share the same UoW TX so orphan claims are avoided by rollback)

  Rollback: 0089_product_label_identity_hardening.down.sql
*/

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_quantity')
    ALTER TABLE dbo.issued_product_labels DROP CONSTRAINT CK_issued_product_labels_quantity;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_quantity_range'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_quantity_range
        CHECK (quantity BETWEEN 1 AND 99999999);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_label_id_len'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_label_id_len
        CHECK (LEN(label_id) = 10);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_checksum_len'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_checksum_len
        CHECK (LEN(checksum) = 1);
GO
GO

-- ----- folded from 0090_local_csv_product_label_id.sql -----
/*
  0090_local_csv_product_label_id.sql

  Persist optional D1 physical product label_id on local CSV import rows and
  productive results (schema 1.1). Nullable for legacy schema 1 / empty cells.

  Rollback: 0090_local_csv_product_label_id.down.sql
*/

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD label_id NVARCHAR(10) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD label_id NVARCHAR(10) NULL;
END;
GO
GO

-- ----- folded from 0091_client_position_label_hierarchy.sql -----
/*
  0091_client_position_label_hierarchy.sql

  Optional pallet/side/level/marker hierarchy columns on client_position_labels
  for positioning label payload V2.

  Rollback: 0091_client_position_label_hierarchy.down.sql
*/

IF COL_LENGTH(N'dbo.client_position_labels', N'pallet') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD pallet NVARCHAR(64) NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'side') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD side VARCHAR(8) NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'level') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD level INT NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'marker_index') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD marker_index INT NULL;
END;
GO

IF COL_LENGTH(N'dbo.client_position_labels', N'marker_total') IS NULL
BEGIN
    ALTER TABLE dbo.client_position_labels ADD marker_total INT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_side'
)
    ALTER TABLE dbo.client_position_labels
        ADD CONSTRAINT CK_client_position_labels_side
        CHECK (side IS NULL OR side IN ('LEFT', 'RIGHT'));
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_level'
)
    ALTER TABLE dbo.client_position_labels
        ADD CONSTRAINT CK_client_position_labels_level
        CHECK (level IS NULL OR level >= 1);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_client_position_labels_marker'
)
    ALTER TABLE dbo.client_position_labels
        ADD CONSTRAINT CK_client_position_labels_marker
        CHECK (
            (marker_index IS NULL AND marker_total IS NULL)
            OR (
                marker_index IS NOT NULL
                AND marker_total IS NOT NULL
                AND marker_index >= 1
                AND marker_total >= 1
                AND marker_index <= marker_total
            )
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_client_position_labels_client_hierarchy'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE NONCLUSTERED INDEX IX_client_position_labels_client_hierarchy
        ON dbo.client_position_labels(client_id, pallet, side, level);
GO
GO

-- ----- folded from 0092_client_position_label_active_marker_unique.sql -----
/*
  0092_client_position_label_active_marker_unique.sql

  Enforce one ACTIVE marker identity per (client_id, pallet, side, level, marker_index).
  Reprint must invalidate the previous ACTIVE label before creating a replacement.

  Rollback: 0092_client_position_label_active_marker_unique.down.sql
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_active_marker'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_labels_active_marker
        ON dbo.client_position_labels(client_id, pallet, side, level, marker_index)
        WHERE status = 'ACTIVE' AND pallet IS NOT NULL;
GO
GO

-- ----- folded from 0093_local_csv_position_payload.sql -----
/*
  0093_local_csv_position_payload.sql

  Optional positioning label id + raw DINAMIC_POSITION payload on local CSV
  import rows and productive results.

  Rollback: 0093_local_csv_position_payload.down.sql
*/

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'position_label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD position_label_id NVARCHAR(64) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'position_payload_raw') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD position_payload_raw NVARCHAR(MAX) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD position_label_id NVARCHAR(64) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_payload_raw') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD position_payload_raw NVARCHAR(MAX) NULL;
END;
GO
GO

-- ----- folded from 0094_local_csv_multi_product_secondary.sql -----
/*
  Version 0094 — local CSV productive uniqueness by label_id (multi-product per photo).

  Before: UNIQUE(capture_session_id, capture_photo_id) collapsed N D1 products on one photo.
  After:  UNIQUE filtered on (capture_session_id, label_id) when label_id present;
          legacy/position rows without label_id use import_row_id uniqueness only
          (plus application-level secondary_key for cross-import conflicts).
*/

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = N'UX_local_csv_productive_secondary'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT UX_local_csv_productive_secondary;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_import_rows_imported_secondary'
      AND object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
)
BEGIN
    DROP INDEX UX_local_csv_import_rows_imported_secondary ON dbo.local_csv_import_rows;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_productive_label'
      AND object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    -- SQL Server filtered indexes disallow LTRIM/RTRIM (error 10735).
    -- Empty label_id must be normalized to NULL in application code.
    CREATE UNIQUE INDEX UX_local_csv_productive_label
        ON dbo.local_csv_productive_results (capture_session_id, label_id)
        WHERE label_id IS NOT NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_import_rows_imported_label'
      AND object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
)
BEGIN
    CREATE UNIQUE INDEX UX_local_csv_import_rows_imported_label
        ON dbo.local_csv_import_rows (capture_session_id, label_id)
        WHERE status = N'IMPORTED'
          AND label_id IS NOT NULL;
END
GO
GO

-- ----- folded from 0095_aisle_scoped_counted_product_labels.sql -----
/*
  Version 0095 — D1 label_id count-once uniqueness is aisle-scoped (pasillo), not inventory.

  Before: UNIQUE(inventory_id, label_id) blocked the same physical sticker across aisles
          in one inventory (and reprocess of another pasillo reused prior claims).
  After:  UNIQUE(aisle_id, label_id); inventory_id retained for audit/traceability.
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
      AND name = N'aisle_id'
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        ADD aisle_id VARCHAR(36) NULL;
END
GO

-- Backfill from job target (CODE_SCAN / pipeline claims).
UPDATE icpl
SET aisle_id = j.target_id
FROM dbo.inventory_counted_product_labels AS icpl
INNER JOIN dbo.inventory_jobs AS j
    ON j.id = icpl.first_job_id
   AND j.target_type = N'aisle'
WHERE icpl.aisle_id IS NULL
  AND NULLIF(LTRIM(RTRIM(icpl.first_job_id)), N'') IS NOT NULL;
GO

-- Backfill remaining from first position.
UPDATE icpl
SET aisle_id = p.aisle_id
FROM dbo.inventory_counted_product_labels AS icpl
INNER JOIN dbo.positions AS p
    ON p.id = icpl.first_position_id
WHERE icpl.aisle_id IS NULL;
GO

-- Orphan claims that cannot be scoped must not block the new unique index.
DELETE FROM dbo.inventory_counted_product_labels
WHERE aisle_id IS NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    DROP INDEX UQ_icpl_inventory_label ON dbo.inventory_counted_product_labels;
END
GO

IF EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
      AND name = N'aisle_id'
      AND is_nullable = 1
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        ALTER COLUMN aisle_id VARCHAR(36) NOT NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_icpl_aisle'
      AND parent_object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    ALTER TABLE dbo.inventory_counted_product_labels
        ADD CONSTRAINT FK_icpl_aisle
            FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_icpl_aisle_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_icpl_aisle_label
        ON dbo.inventory_counted_product_labels(aisle_id, label_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_icpl_inventory_label'
      AND object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_icpl_inventory_label
        ON dbo.inventory_counted_product_labels(inventory_id, label_id);
END
GO
GO

-- <<< FOLDED_FROM_MIGRATIONS_END
