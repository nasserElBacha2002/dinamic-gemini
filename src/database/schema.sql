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

-- v3.0 — Jobs (Épica 4; domain Job entity, distinct from legacy jobs table)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'v3_jobs')
BEGIN
    CREATE TABLE v3_jobs (
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
    CREATE INDEX IX_v3_jobs_target ON v3_jobs(target_type, target_id);
END;
GO
