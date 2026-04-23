/*
G3 — temporal grouping for capture session items (inventory-level).

Adds capture_session_groups and optional group_id on items. Filtered-index rules do not apply here.

FK items→groups uses ON DELETE NO ACTION (not SET NULL) to avoid SQL Server error 1785
(multiple cascade paths: sessions→items CASCADE + sessions→groups CASCADE + items→groups).
Application clears group_id before deleting groups (ComputeCaptureSessionGroups).
*/

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
