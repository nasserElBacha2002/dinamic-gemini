/*
  Version 0104 — Preliminary position sync V2 diagnostic evidence.

  Additive only. These columns record mobile claims and the server validator
  outcome; they do not create or update operational positions.
*/

IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_local_recognition_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_local_recognition_id VARCHAR(128) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_raw_code') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_raw_code NVARCHAR(4000) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_claimed_normalized_code') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_claimed_normalized_code NVARCHAR(64) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_claimed_remote_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_claimed_remote_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_claimed_remote_label_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_claimed_remote_label_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_source') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_source VARCHAR(32) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_profile_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_profile_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_profile_version') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_profile_version INT NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_client_supplier_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_client_supplier_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_signature_present') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_signature_present BIT NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_signature_verification') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_signature_verification VARCHAR(32) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_captured_at') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_captured_at DATETIME2 NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_result_status') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_result_status VARCHAR(32) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_result_error_code') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_result_error_code VARCHAR(64) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_result_retryable') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_result_retryable BIT NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_normalized_code') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_normalized_code NVARCHAR(64) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_remote_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_remote_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_remote_label_id') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_remote_label_id VARCHAR(36) NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_validated_at') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections ADD position_validated_at DATETIME2 NULL;
GO
IF COL_LENGTH(N'dbo.mobile_preliminary_detections', N'position_reconciliation_revision') IS NULL
    ALTER TABLE dbo.mobile_preliminary_detections
        ADD position_reconciliation_revision INT NOT NULL
            CONSTRAINT DF_mpd_position_reconciliation_revision DEFAULT (0);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_mpd_position_reconciliation_revision'
      AND parent_object_id = OBJECT_ID('dbo.mobile_preliminary_detections')
)
    ALTER TABLE dbo.mobile_preliminary_detections
        ADD CONSTRAINT CK_mpd_position_reconciliation_revision
            CHECK (position_reconciliation_revision >= 0);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_mpd_position_local_recognition'
      AND object_id = OBJECT_ID('dbo.mobile_preliminary_detections')
)
    CREATE NONCLUSTERED INDEX IX_mpd_position_local_recognition
        ON dbo.mobile_preliminary_detections(position_local_recognition_id)
        WHERE position_local_recognition_id IS NOT NULL;
GO
