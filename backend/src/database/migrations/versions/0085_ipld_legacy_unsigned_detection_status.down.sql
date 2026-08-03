/*
  Rollback 0085 — restore CK_ipld_detection_status without LEGACY_UNSIGNED_REQUIRES_REVIEW.
*/

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = N'CK_ipld_detection_status'
      AND parent_object_id = OBJECT_ID(N'dbo.image_position_label_detections')
)
    ALTER TABLE dbo.image_position_label_detections DROP CONSTRAINT CK_ipld_detection_status;
GO

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
GO
