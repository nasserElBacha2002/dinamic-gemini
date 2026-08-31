/*
  Rollback 0103 — restore NOT NULL on authoritative_local_code_scan_results.internal_code.
  Fails if any NULL rows exist; backfill empty string before running if needed.
*/

IF COL_LENGTH(N'dbo.authoritative_local_code_scan_results', N'internal_code') IS NOT NULL
BEGIN
    UPDATE dbo.authoritative_local_code_scan_results
       SET internal_code = N''
     WHERE internal_code IS NULL;

    ALTER TABLE dbo.authoritative_local_code_scan_results
        ALTER COLUMN internal_code NVARCHAR(64) NOT NULL;
END;
GO
