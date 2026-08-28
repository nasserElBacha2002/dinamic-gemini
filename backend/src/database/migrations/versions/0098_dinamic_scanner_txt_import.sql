/*
  Version 0098 — Dinamic Scanner TXT import metadata + ingestion_source expansion.

  - Persist staged scanner TXT metadata on local_csv_imports.
  - Allow DINAMIC_SCANNER_TXT ingestion_source on import rows and productive results.
*/

IF COL_LENGTH(N'dbo.local_csv_imports', N'source_metadata_json') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_imports
        ADD source_metadata_json NVARCHAR(MAX) NULL;
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_import_rows_ingestion_source'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_import_rows', N'U')
)
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        DROP CONSTRAINT CK_local_csv_import_rows_ingestion_source;
END;
GO

IF OBJECT_ID(N'dbo.local_csv_import_rows', N'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.check_constraints
       WHERE name = N'CK_local_csv_import_rows_ingestion_source'
         AND parent_object_id = OBJECT_ID(N'dbo.local_csv_import_rows', N'U')
   )
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD CONSTRAINT CK_local_csv_import_rows_ingestion_source
            CHECK (ingestion_source IN (N'LOCAL_CSV_IMPORT', N'DINAMIC_SCANNER_TXT'));
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_local_csv_productive_ingestion'
      AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results', N'U')
)
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT CK_local_csv_productive_ingestion;
END;
GO

IF OBJECT_ID(N'dbo.local_csv_productive_results', N'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.check_constraints
       WHERE name = N'CK_local_csv_productive_ingestion'
         AND parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results', N'U')
   )
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD CONSTRAINT CK_local_csv_productive_ingestion
            CHECK (ingestion_source IN (N'LOCAL_CSV_IMPORT', N'DINAMIC_SCANNER_TXT'));
END;
GO
