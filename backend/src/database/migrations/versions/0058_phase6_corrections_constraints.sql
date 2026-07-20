-- Phase 6 corrections: persisted external request integrity + annotation scope index.
-- Additive / idempotent for SQL Server.
-- Note: filtered ACTIVE uniqueness already exists as UQ_sep_one_active (0057).

-- PERSISTED requests must carry position_id or active_result_id.
IF OBJECT_ID('external_image_analysis_requests', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = 'CK_external_image_analysis_requests_persisted_result'
          AND parent_object_id = OBJECT_ID('external_image_analysis_requests')
   )
BEGIN
    ALTER TABLE external_image_analysis_requests WITH NOCHECK
    ADD CONSTRAINT CK_external_image_analysis_requests_persisted_result
    CHECK (
        status <> 'PERSISTED'
        OR position_id IS NOT NULL
        OR active_result_id IS NOT NULL
    );
END
GO

-- Annotation profile scope helper index (tenant lookups by profile).
IF OBJECT_ID('supplier_reference_annotations', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_supplier_reference_annotations_profile'
          AND object_id = OBJECT_ID('supplier_reference_annotations')
   )
BEGIN
    CREATE INDEX IX_supplier_reference_annotations_profile
        ON supplier_reference_annotations(profile_id, template_image_id)
        WHERE profile_id IS NOT NULL;
END
GO
