/*
  Rollback 0086_local_csv_imports — drop productive results then staging tables.
*/

IF OBJECT_ID(N'dbo.local_csv_productive_results', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.local_csv_productive_results;
END;
GO

IF OBJECT_ID(N'dbo.local_csv_import_rows', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.local_csv_import_rows;
END;
GO

IF OBJECT_ID(N'dbo.local_csv_imports', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.local_csv_imports;
END;
GO
