/*
  0076_ordered_capture_processing_job_link.sql

  Phase 1 unblock — link ordered capture sessions to the inventory job that
  reserved SEALED → PROCESSING (nullable FK; set after job row exists).

  Apply:
    Run via the UP-only migration runner (db_migrate apply / service.apply_pending).
    Idempotent: IF NOT EXISTS / IF EXISTS guards throughout.

  Rollback (manual, not runner-driven):
    Execute 0076_ordered_capture_processing_job_link.down.sql against the same DB.
*/

-- ---------------------------------------------------------------------------
-- ordered_capture_sessions.processing_job_id → inventory_jobs(id)
-- ---------------------------------------------------------------------------
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
