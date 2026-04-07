-- Prompt traceability for multi-provider runs (align with Job domain + API).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'prompt_version')
    ALTER TABLE inventory_jobs ADD prompt_version NVARCHAR(256) NULL;
