-- v3.3.2 — Manual retry lineage for inventory jobs
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'retry_of_job_id')
    ALTER TABLE inventory_jobs ADD retry_of_job_id VARCHAR(36) NULL;
GO
