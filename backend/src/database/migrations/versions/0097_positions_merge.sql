/*
  Version 0097 — Operator-driven position merge (additive).

  merged_into_position_id NULL = active independent result (default)
  merged_into_position_id set  = source was merged into the referenced survivor
  merged_at                    = when the merge completed

  Sources are never hard-deleted; list/export hide rows with merged_into set.
  Evidence / product_records / review_actions remain intact.
*/

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_into_position_id'
)
BEGIN
    ALTER TABLE dbo.positions ADD merged_into_position_id VARCHAR(36) NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys
    WHERE name = N'FK_positions_merged_into' AND parent_object_id = OBJECT_ID(N'dbo.positions')
)
BEGIN
    ALTER TABLE dbo.positions
        ADD CONSTRAINT FK_positions_merged_into
        FOREIGN KEY (merged_into_position_id) REFERENCES dbo.positions(id);
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_at'
)
BEGIN
    ALTER TABLE dbo.positions ADD merged_at DATETIME2 NULL;
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints
    WHERE name = N'CK_positions_merged_into_not_self'
      AND parent_object_id = OBJECT_ID(N'dbo.positions')
)
BEGIN
    ALTER TABLE dbo.positions
        ADD CONSTRAINT CK_positions_merged_into_not_self
        CHECK (
            merged_into_position_id IS NULL
            OR merged_into_position_id <> id
        );
END
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.positions')
      AND name = N'IX_positions_merged_into'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_positions_merged_into
        ON dbo.positions (aisle_id, merged_into_position_id)
        WHERE merged_into_position_id IS NOT NULL;
END
GO
