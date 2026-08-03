/*
  0081_image_position_label_detections_job_scope.sql

  Phase 3 corrections:
  - Job-scoped unique identity (preserve history across jobs)
  - detection_status CHECK
  - Drop pre-0081 asset-only unique index

  Rollback: 0081_image_position_label_detections_job_scope.down.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    DROP INDEX UQ_ipld_asset_detector_hash_status ON dbo.image_position_label_detections;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_ipld_job_asset_detector_hash_status'
      AND object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ipld_job_asset_detector_hash_status
        ON dbo.image_position_label_detections(
            job_id,
            source_asset_id,
            detector_version,
            detection_status,
            raw_payload_hash
        );
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_ipld_detection_status'
      AND parent_object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
BEGIN
    ALTER TABLE dbo.image_position_label_detections WITH NOCHECK
    ADD CONSTRAINT CK_ipld_detection_status CHECK (
        detection_status IN (
            'VALID',
            'INVALID_JSON',
            'INVALID_TYPE',
            'UNSUPPORTED_VERSION',
            'UNSUPPORTED_LEGACY_PAYLOAD',
            'MISSING_LABEL_ID',
            'MISSING_SIGNATURE',
            'INVALID_SIGNATURE',
            'UNKNOWN_KEY_VERSION',
            'SIGNATURE_VALIDATION_SKIPPED',
            'LABEL_NOT_FOUND',
            'LABEL_INVALIDATED',
            'CLIENT_MISMATCH',
            'DUPLICATE_POSITION_CODES',
            'AMBIGUOUS_POSITION_DETECTION',
            'PAYLOAD_TOO_LARGE',
            'DECODE_TIMEOUT',
            'DETECTION_FAILED',
            'DETECTION_CONTEXT_INVALID',
            'NO_LABEL',
            'FEATURE_DISABLED'
        )
    );
END
GO
