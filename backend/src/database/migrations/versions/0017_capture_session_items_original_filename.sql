-- Sprint 2 — Optional client filename on capture session staging items (audit / future UI).

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('capture_session_items') AND name = 'original_filename'
)
    ALTER TABLE capture_session_items ADD original_filename NVARCHAR(512) NULL;
GO
