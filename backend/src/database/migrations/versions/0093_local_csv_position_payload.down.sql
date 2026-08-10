/*
  0093_local_csv_position_payload.down.sql
*/

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_payload_raw') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results DROP COLUMN position_payload_raw;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_label_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results DROP COLUMN position_label_id;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'position_payload_raw') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows DROP COLUMN position_payload_raw;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'position_label_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows DROP COLUMN position_label_id;
END;
GO
