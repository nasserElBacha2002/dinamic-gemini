/*
G4 — assign capture session groups to aisles (operational bridge before materialization).

Adds nullable aisle assignment columns on capture_session_groups.
FK uses ON DELETE NO ACTION to avoid SQL Server cascade path issues with aisles.
*/

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
