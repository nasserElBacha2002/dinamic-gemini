-- G5 — idempotent group materialization: at most one SourceAsset per capture_session_item
-- when the column is set (grouping-first materialize path).

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
