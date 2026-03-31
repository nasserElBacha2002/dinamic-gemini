-- v3.3.1 — On-demand worker lifecycle metadata and stale reconciliation support
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'started_at')
    ALTER TABLE inventory_jobs ADD started_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'finished_at')
    ALTER TABLE inventory_jobs ADD finished_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'last_heartbeat_at')
    ALTER TABLE inventory_jobs ADD last_heartbeat_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'cancel_requested_at')
    ALTER TABLE inventory_jobs ADD cancel_requested_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_stage')
    ALTER TABLE inventory_jobs ADD current_stage NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_substep')
    ALTER TABLE inventory_jobs ADD current_substep NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'current_step_started_at')
    ALTER TABLE inventory_jobs ADD current_step_started_at DATETIME2 NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'attempt_count')
    ALTER TABLE inventory_jobs ADD attempt_count INT NOT NULL DEFAULT 1;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'failure_code')
    ALTER TABLE inventory_jobs ADD failure_code VARCHAR(64) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'failure_message')
    ALTER TABLE inventory_jobs ADD failure_message NVARCHAR(2048) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'execution_id')
    ALTER TABLE inventory_jobs ADD execution_id VARCHAR(64) NULL;
GO
