-- Phase 1 — Multi-run persistence: nullable job_id on result tables + inventory_jobs identity columns.
-- No backfill; legacy rows keep job_id NULL.

-- inventory_jobs: indexed run identity (tuning lives in engine_params_json)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'provider_name')
    ALTER TABLE inventory_jobs ADD provider_name NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'model_name')
    ALTER TABLE inventory_jobs ADD model_name NVARCHAR(256) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'prompt_key')
    ALTER TABLE inventory_jobs ADD prompt_key NVARCHAR(256) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'engine_params_json')
    ALTER TABLE inventory_jobs ADD engine_params_json NVARCHAR(MAX) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_inventory_jobs_provider_model_prompt' AND object_id = OBJECT_ID('inventory_jobs'))
    CREATE INDEX IX_inventory_jobs_provider_model_prompt ON inventory_jobs(provider_name, model_name, prompt_key);
GO

-- positions
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'job_id')
BEGIN
    ALTER TABLE positions ADD job_id VARCHAR(36) NULL;
    ALTER TABLE positions ADD CONSTRAINT FK_positions_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_positions_aisle_job_id' AND object_id = OBJECT_ID('positions'))
    CREATE INDEX IX_positions_aisle_job_id ON positions(aisle_id, job_id);
GO

-- raw_labels
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('raw_labels') AND name = 'job_id')
BEGIN
    ALTER TABLE raw_labels ADD job_id VARCHAR(36) NULL;
    ALTER TABLE raw_labels ADD CONSTRAINT FK_raw_labels_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_raw_labels_scope_job' AND object_id = OBJECT_ID('raw_labels'))
    CREATE INDEX IX_raw_labels_scope_job ON raw_labels(inventory_id, aisle_id, job_id);
GO

-- normalized_labels
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('normalized_labels') AND name = 'job_id')
BEGIN
    ALTER TABLE normalized_labels ADD job_id VARCHAR(36) NULL;
    ALTER TABLE normalized_labels ADD CONSTRAINT FK_normalized_labels_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_normalized_labels_scope_job' AND object_id = OBJECT_ID('normalized_labels'))
    CREATE INDEX IX_normalized_labels_scope_job ON normalized_labels(inventory_id, aisle_id, job_id);
GO

-- final_count_records
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('final_count_records') AND name = 'job_id')
BEGIN
    ALTER TABLE final_count_records ADD job_id VARCHAR(36) NULL;
    ALTER TABLE final_count_records ADD CONSTRAINT FK_final_count_inventory_job FOREIGN KEY (job_id) REFERENCES inventory_jobs(id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_final_count_scope_job' AND object_id = OBJECT_ID('final_count_records'))
    CREATE INDEX IX_final_count_scope_job ON final_count_records(inventory_id, aisle_id, job_id);
GO
