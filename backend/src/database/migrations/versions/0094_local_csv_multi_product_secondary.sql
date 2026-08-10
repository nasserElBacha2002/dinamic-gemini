/*
  Version 0094 — local CSV productive uniqueness by label_id (multi-product per photo).

  Before: UNIQUE(capture_session_id, capture_photo_id) collapsed N D1 products on one photo.
  After:  UNIQUE filtered on (capture_session_id, label_id) when label_id present;
          legacy/position rows without label_id use import_row_id uniqueness only
          (plus application-level secondary_key for cross-import conflicts).
*/

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = N'UX_local_csv_productive_secondary'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT UX_local_csv_productive_secondary;
END
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_import_rows_imported_secondary'
      AND object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
)
BEGIN
    DROP INDEX UX_local_csv_import_rows_imported_secondary ON dbo.local_csv_import_rows;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_productive_label'
      AND object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
)
BEGIN
    -- SQL Server filtered indexes disallow LTRIM/RTRIM (error 10735).
    -- Empty label_id must be normalized to NULL in application code.
    CREATE UNIQUE INDEX UX_local_csv_productive_label
        ON dbo.local_csv_productive_results (capture_session_id, label_id)
        WHERE label_id IS NOT NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UX_local_csv_import_rows_imported_label'
      AND object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
)
BEGIN
    CREATE UNIQUE INDEX UX_local_csv_import_rows_imported_label
        ON dbo.local_csv_import_rows (capture_session_id, label_id)
        WHERE status = N'IMPORTED'
          AND label_id IS NOT NULL;
END
GO
