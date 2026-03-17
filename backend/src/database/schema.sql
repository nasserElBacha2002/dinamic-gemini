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
            updated_at DATETIME2 NOT NULL
        );
        CREATE INDEX IX_inventory_jobs_target ON inventory_jobs(target_type, target_id);
    END
END;
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
        mime_type VARCHAR(128) NOT NULL,
        uploaded_at DATETIME2 NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        CONSTRAINT FK_source_assets_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_source_assets_aisle_id ON source_assets(aisle_id);
END;
GO

-- v3.0 — Positions (Épica 6, Documento técnico §7.4)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'positions')
BEGIN
    CREATE TABLE positions (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
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
        source_asset_id VARCHAR(36) NULL,
        is_primary BIT NOT NULL DEFAULT 0,
        frame_index INT NULL,
        timestamp_ms INT NULL,
        bbox_json NVARCHAR(MAX) NULL,
        quality_score FLOAT NULL
    );
END;
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
