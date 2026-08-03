/*
  0081_image_position_label_detections_job_scope.down.sql

  Manual rollback for 0081 (restore pre-correction unique index shape).
*/

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_ipld_detection_status'
      AND parent_object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    ALTER TABLE dbo.image_position_label_detections DROP CONSTRAINT CK_ipld_detection_status;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_job_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    DROP INDEX UQ_ipld_job_asset_detector_hash_status ON dbo.image_position_label_detections;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ipld_asset_detector_hash_status
        ON dbo.image_position_label_detections(
            source_asset_id,
            detector_version,
            detection_status,
            raw_payload_hash
        );
GO
