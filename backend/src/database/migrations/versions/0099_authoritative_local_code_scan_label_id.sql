/*
  Version 0099 — Additive label_id on authoritative local CODE_SCAN results.

  Enables aisle-scoped counted-product-label claims when Mobile authoritative
  apply persists ProductRecords (cross-source dedupe with CSV/TXT/CV).

  - Nullable: historical rows remain valid without backfill.
  - No unique constraint on label_id alone (counted labels already UNIQUE(aisle_id, label_id)).

  Rollback: 0099_authoritative_local_code_scan_label_id.down.sql
*/

IF COL_LENGTH(N'dbo.authoritative_local_code_scan_results', N'label_id') IS NULL
BEGIN
    ALTER TABLE dbo.authoritative_local_code_scan_results
        ADD label_id NVARCHAR(64) NULL;
END;
GO

IF OBJECT_ID(N'dbo.authoritative_local_code_scan_results', N'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM sys.indexes
       WHERE name = N'IX_alcsr_aisle_label'
         AND object_id = OBJECT_ID(N'dbo.authoritative_local_code_scan_results')
   )
BEGIN
    CREATE NONCLUSTERED INDEX IX_alcsr_aisle_label
        ON dbo.authoritative_local_code_scan_results (aisle_id, label_id)
        WHERE label_id IS NOT NULL;
END;
GO
