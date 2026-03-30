-- v3.3.0 — Provider-aware artifact metadata (S3 foundation, additive and backward-compatible)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'storage_provider')
    ALTER TABLE source_assets ADD storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'storage_bucket')
    ALTER TABLE source_assets ADD storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'storage_key')
    ALTER TABLE source_assets ADD storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'content_type')
    ALTER TABLE source_assets ADD content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'file_size_bytes')
    ALTER TABLE source_assets ADD file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('source_assets') AND name = 'etag')
    ALTER TABLE source_assets ADD etag NVARCHAR(128) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'storage_provider')
    ALTER TABLE inventory_visual_references ADD storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'storage_bucket')
    ALTER TABLE inventory_visual_references ADD storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'storage_key')
    ALTER TABLE inventory_visual_references ADD storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'content_type')
    ALTER TABLE inventory_visual_references ADD content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'file_size_bytes')
    ALTER TABLE inventory_visual_references ADD file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_visual_references') AND name = 'etag')
    ALTER TABLE inventory_visual_references ADD etag NVARCHAR(128) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'storage_provider')
    ALTER TABLE evidences ADD storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'storage_bucket')
    ALTER TABLE evidences ADD storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'storage_key')
    ALTER TABLE evidences ADD storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'content_type')
    ALTER TABLE evidences ADD content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'file_size_bytes')
    ALTER TABLE evidences ADD file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('evidences') AND name = 'etag')
    ALTER TABLE evidences ADD etag NVARCHAR(128) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_storage_provider')
    ALTER TABLE jobs ADD report_storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_storage_bucket')
    ALTER TABLE jobs ADD report_storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_json_storage_key')
    ALTER TABLE jobs ADD report_json_storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_csv_storage_key')
    ALTER TABLE jobs ADD report_csv_storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_content_type')
    ALTER TABLE jobs ADD report_content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_file_size_bytes')
    ALTER TABLE jobs ADD report_file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'report_etag')
    ALTER TABLE jobs ADD report_etag NVARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'log_storage_provider')
    ALTER TABLE jobs ADD log_storage_provider VARCHAR(16) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'log_storage_bucket')
    ALTER TABLE jobs ADD log_storage_bucket NVARCHAR(255) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_storage_key')
    ALTER TABLE jobs ADD execution_log_storage_key NVARCHAR(1024) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_content_type')
    ALTER TABLE jobs ADD execution_log_content_type VARCHAR(128) NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_file_size_bytes')
    ALTER TABLE jobs ADD execution_log_file_size_bytes BIGINT NULL;
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('jobs') AND name = 'execution_log_etag')
    ALTER TABLE jobs ADD execution_log_etag NVARCHAR(128) NULL;
GO
