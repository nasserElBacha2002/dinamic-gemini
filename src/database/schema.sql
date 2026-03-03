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
