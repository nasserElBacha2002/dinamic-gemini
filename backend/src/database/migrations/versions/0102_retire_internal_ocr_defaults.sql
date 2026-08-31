-- 0102: Retire INTERNAL_OCR as productive default for new aisle processing.
-- Before: client/inventory/aisle configs may store identification_mode=INTERNAL_OCR.
-- After: those configs become CODE_SCAN (Vision after CODE_SCAN when provider configured).
-- Does NOT rewrite historical inventory_jobs rows (legacy INTERNAL_OCR jobs remain runnable).
-- Rollback: restore INTERNAL_OCR from backup if required (see .down.sql).

UPDATE clients
SET default_identification_mode = 'CODE_SCAN'
WHERE default_identification_mode = 'INTERNAL_OCR';
GO

UPDATE inventories
SET identification_mode = 'CODE_SCAN'
WHERE identification_mode = 'INTERNAL_OCR';
GO

UPDATE aisles
SET identification_mode = 'CODE_SCAN'
WHERE identification_mode = 'INTERNAL_OCR';
GO
