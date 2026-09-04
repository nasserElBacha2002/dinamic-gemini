/*
  Version 0103 — Allow NULL internal_code on authoritative local CODE_SCAN results.

  Supplier identity-only ITEM labels (MINIMAL) may have label_id without SKU/internal_code.
  Legacy Dinamic/trade-item rows continue to require internal_code at the application layer.

  Rollback: 0103_authoritative_internal_code_nullable.down.sql
*/

IF COL_LENGTH(N'dbo.authoritative_local_code_scan_results', N'internal_code') IS NOT NULL
BEGIN
    ALTER TABLE dbo.authoritative_local_code_scan_results
        ALTER COLUMN internal_code NVARCHAR(64) NULL;
END;
GO
