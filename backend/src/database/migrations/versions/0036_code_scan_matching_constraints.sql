-- Phase 4 corrections — CHECK constraints for code scan match fields.
-- Positions use soft-delete (status=deleted); FK kept without ON DELETE (audit snapshot).

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_match_status'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_match_status
    CHECK (
        match_status IS NULL OR match_status IN (
            'not_evaluated',
            'matched',
            'no_match',
            'multiple_candidates',
            'conflict'
        )
    );
END;
GO

IF OBJECT_ID('aisle_code_scan_detections', 'U') IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM sys.check_constraints
       WHERE name = 'CK_aisle_code_scan_detections_match_type'
         AND parent_object_id = OBJECT_ID('aisle_code_scan_detections')
   )
BEGIN
    ALTER TABLE aisle_code_scan_detections
    ADD CONSTRAINT CK_aisle_code_scan_detections_match_type
    CHECK (
        match_type IS NULL OR match_type IN (
            'barcode_exact',
            'sku_exact',
            'internal_code_exact',
            'position_code_exact',
            'pallet_id_exact',
            'qr_payload_sku_exact',
            'qr_payload_barcode_exact',
            'multiple_candidates',
            'no_match'
        )
    );
END;
GO
