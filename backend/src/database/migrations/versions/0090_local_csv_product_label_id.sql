/*
  0090_local_csv_product_label_id.sql

  Persist optional D1 physical product label_id on local CSV import rows and
  productive results (schema 1.1). Nullable for legacy schema 1 / empty cells.

  Rollback: 0090_local_csv_product_label_id.down.sql
*/

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD label_id NVARCHAR(10) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD label_id NVARCHAR(10) NULL;
END;
GO
