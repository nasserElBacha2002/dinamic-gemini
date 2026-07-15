-- Additive idempotency keys for aisle source-asset multipart uploads (per request / client file).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'upload_batch_id')
    ALTER TABLE source_assets ADD upload_batch_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'upload_client_file_id')
    ALTER TABLE source_assets ADD upload_client_file_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_source_assets_aisle_upload_batch_client'
      AND object_id = OBJECT_ID('source_assets')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_source_assets_aisle_upload_batch_client
        ON source_assets(aisle_id, upload_batch_id, upload_client_file_id)
        WHERE upload_batch_id IS NOT NULL AND upload_client_file_id IS NOT NULL;
GO
