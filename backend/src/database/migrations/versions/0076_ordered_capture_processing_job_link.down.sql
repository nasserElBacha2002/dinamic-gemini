/*
  0076_ordered_capture_processing_job_link.down.sql

  Manual rollback for 0076 only (not executed by the UP-only migration runner).

  Reverses:
  - IX_ordered_capture_sessions_processing_job
  - FK_ordered_capture_sessions_processing_job
  - processing_job_id column

  WARNING: DROP COLUMN discards processing_job_id links.
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_ordered_capture_sessions_processing_job'
      AND object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
)
    DROP INDEX IX_ordered_capture_sessions_processing_job
        ON dbo.ordered_capture_sessions;
GO

IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE name = N'FK_ordered_capture_sessions_processing_job'
)
    ALTER TABLE dbo.ordered_capture_sessions
        DROP CONSTRAINT FK_ordered_capture_sessions_processing_job;
GO

IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.ordered_capture_sessions')
      AND name = N'processing_job_id'
)
    ALTER TABLE dbo.ordered_capture_sessions DROP COLUMN processing_job_id;
GO
