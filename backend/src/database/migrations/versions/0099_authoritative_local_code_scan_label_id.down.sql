/*
  Rollback 0099 — drop label_id from authoritative_local_code_scan_results.
*/

IF EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_alcsr_aisle_label'
      AND object_id = OBJECT_ID(N'dbo.authoritative_local_code_scan_results')
)
BEGIN
    DROP INDEX IX_alcsr_aisle_label ON dbo.authoritative_local_code_scan_results;
END;
GO

IF COL_LENGTH(N'dbo.authoritative_local_code_scan_results', N'label_id') IS NOT NULL
BEGIN
    ALTER TABLE dbo.authoritative_local_code_scan_results
        DROP COLUMN label_id;
END;
GO
