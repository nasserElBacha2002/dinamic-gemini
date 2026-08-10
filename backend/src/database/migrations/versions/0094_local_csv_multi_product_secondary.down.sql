/*
  Rollback 0094 — restore photo-based secondary uniqueness (pre multi-product).
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_productive_label'
      AND object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    DROP INDEX UX_local_csv_productive_label ON dbo.local_csv_productive_results;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_import_rows_imported_label'
      AND object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
)
BEGIN
    DROP INDEX UX_local_csv_import_rows_imported_label ON dbo.local_csv_import_rows;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = N'UX_local_csv_productive_secondary'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT UX_local_csv_productive_secondary
        UNIQUE (capture_session_id, capture_photo_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_import_rows_imported_secondary'
      AND object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
)
BEGIN
    CREATE UNIQUE INDEX UX_local_csv_import_rows_imported_secondary
        ON dbo.local_csv_import_rows (capture_session_id, capture_photo_id)
        WHERE status = N'IMPORTED';
END
GO
