-- Phase 7 corrections: adoption content_hash for idempotent payload replay.
-- Additive. Do not alter 0067 if already applied.
-- Formal rollback (dev/test only):
--   ALTER TABLE server_reprocess_adoptions DROP CONSTRAINT UQ_sra_adoption_hash;
--   ALTER TABLE server_reprocess_adoptions DROP COLUMN content_hash;

IF OBJECT_ID('server_reprocess_adoptions', 'U') IS NOT NULL
   AND COL_LENGTH('server_reprocess_adoptions', 'content_hash') IS NULL
BEGIN
    ALTER TABLE server_reprocess_adoptions
        ADD content_hash VARCHAR(80) NOT NULL
            CONSTRAINT DF_sra_content_hash DEFAULT ('');
END
GO

IF OBJECT_ID('server_reprocess_adoptions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_sra_run_content_hash'
          AND object_id = OBJECT_ID('server_reprocess_adoptions')
   )
    CREATE INDEX IX_sra_run_content_hash
        ON server_reprocess_adoptions (run_id, content_hash);
GO

IF OBJECT_ID('server_reprocess_runs', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srr_aisle_status'
          AND object_id = OBJECT_ID('server_reprocess_runs')
   )
    CREATE INDEX IX_srr_aisle_status
        ON server_reprocess_runs (aisle_id, status, requested_at DESC);
GO
