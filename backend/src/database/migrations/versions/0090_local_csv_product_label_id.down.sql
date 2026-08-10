/*
  0090_local_csv_product_label_id.down.sql
*/

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'label_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results DROP COLUMN label_id;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'label_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows DROP COLUMN label_id;
END;
GO
