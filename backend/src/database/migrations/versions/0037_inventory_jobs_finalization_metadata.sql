-- Phase 3.2 — Job finalization progress metadata on inventory_jobs
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_status')
    ALTER TABLE inventory_jobs ADD finalization_status VARCHAR(32) NOT NULL DEFAULT 'not_started';
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_finalization_step')
    ALTER TABLE inventory_jobs ADD current_finalization_step VARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'last_completed_finalization_step')
    ALTER TABLE inventory_jobs ADD last_completed_finalization_step VARCHAR(64) NOT NULL DEFAULT 'none';
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_error_code')
    ALTER TABLE inventory_jobs ADD finalization_error_code VARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_error_metadata')
    ALTER TABLE inventory_jobs ADD finalization_error_metadata NVARCHAR(MAX) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_started_at')
    ALTER TABLE inventory_jobs ADD finalization_started_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finalization_completed_at')
    ALTER TABLE inventory_jobs ADD finalization_completed_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'domain_persisted_at')
    ALTER TABLE inventory_jobs ADD domain_persisted_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'artifacts_published_at')
    ALTER TABLE inventory_jobs ADD artifacts_published_at DATETIME2 NULL;
GO
