-- Inventory processing mode: production (operational default) vs test (benchmark / multi-run).
-- Existing rows are backfilled to `test` so legacy experimental workflows keep working.

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'processing_mode')
    ALTER TABLE inventories ADD processing_mode VARCHAR(20) NULL;
GO

UPDATE inventories SET processing_mode = 'test' WHERE processing_mode IS NULL;
GO

IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'processing_mode' AND is_nullable = 1)
    ALTER TABLE inventories ALTER COLUMN processing_mode VARCHAR(20) NOT NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.default_constraints WHERE parent_object_id = OBJECT_ID('inventories') AND name = 'DF_inventories_processing_mode')
    ALTER TABLE inventories ADD CONSTRAINT DF_inventories_processing_mode DEFAULT ('production') FOR processing_mode;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_provider_name')
    ALTER TABLE inventories ADD primary_provider_name NVARCHAR(100) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_model_name')
    ALTER TABLE inventories ADD primary_model_name NVARCHAR(150) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_prompt_key')
    ALTER TABLE inventories ADD primary_prompt_key NVARCHAR(150) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'primary_prompt_version')
    ALTER TABLE inventories ADD primary_prompt_version NVARCHAR(50) NULL;
GO
