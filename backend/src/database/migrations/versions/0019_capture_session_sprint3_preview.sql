-- Sprint 3 — session clock offset + preview persistence on items (no SourceAsset / no confirm).

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_sessions') AND name = 'clock_offset_seconds'
)
BEGIN
    ALTER TABLE dbo.capture_sessions ADD clock_offset_seconds INT NOT NULL DEFAULT 0;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items') AND name = 'adjusted_capture_time'
)
BEGIN
    ALTER TABLE dbo.capture_session_items ADD adjusted_capture_time DATETIME2 NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items') AND name = 'assignment_reason'
)
BEGIN
    ALTER TABLE dbo.capture_session_items ADD assignment_reason NVARCHAR(512) NULL;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.capture_session_items') AND name = 'preview_target_position_id'
)
BEGIN
    ALTER TABLE dbo.capture_session_items ADD preview_target_position_id VARCHAR(36) NULL;
END;
GO
