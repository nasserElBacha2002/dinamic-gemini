/*
  0093_local_csv_position_payload.sql

  Optional positioning label id + raw DINAMIC_POSITION payload on local CSV
  import rows and productive results.

  Rollback: 0093_local_csv_position_payload.down.sql
*/

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'position_label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD position_label_id NVARCHAR(64) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_import_rows', N'position_payload_raw') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_import_rows
        ADD position_payload_raw NVARCHAR(MAX) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_label_id') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD position_label_id NVARCHAR(64) NULL;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_payload_raw') IS NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results
        ADD position_payload_raw NVARCHAR(MAX) NULL;
END;
GO
