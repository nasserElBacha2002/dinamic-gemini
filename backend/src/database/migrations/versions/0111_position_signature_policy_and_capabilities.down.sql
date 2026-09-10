/*
  Down migration for 0111 — fail-closed.
  Require explicit confirmation via env-style markers in the comment block before running.
  Do NOT run while POSITION_FLEXIBLE_* channel flags or capabilities are in use.
*/

/*
  SAFETY:
  - Take a database backup before running.
  - Confirm POSITION_FLEXIBLE_VALIDATION_ENABLED / channel flags are disabled.
  - Confirm no rows depend on position_flexible_capabilities ENFORCED mode.
*/

IF OBJECT_ID(N'dbo.position_flexible_capabilities', N'U') IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.position_flexible_capabilities WHERE enabled = 1)
    BEGIN
        THROW 51111, N'Cannot drop position_flexible_capabilities while enabled rows exist', 1;
    END

    IF EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'UQ_pfc_scope_key'
          AND object_id = OBJECT_ID(N'dbo.position_flexible_capabilities')
    )
        DROP INDEX UQ_pfc_scope_key ON dbo.position_flexible_capabilities;

    DROP TABLE dbo.position_flexible_capabilities;
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_sep_signature_policy'
      AND parent_object_id = OBJECT_ID(N'dbo.supplier_extraction_profiles')
)
    ALTER TABLE dbo.supplier_extraction_profiles DROP CONSTRAINT CK_sep_signature_policy;
GO

IF EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE name = N'DF_sep_signature_policy'
      AND parent_object_id = OBJECT_ID(N'dbo.supplier_extraction_profiles')
)
    ALTER TABLE dbo.supplier_extraction_profiles DROP CONSTRAINT DF_sep_signature_policy;
GO

IF COL_LENGTH(N'dbo.supplier_extraction_profiles', N'signature_policy') IS NOT NULL
    ALTER TABLE dbo.supplier_extraction_profiles DROP COLUMN signature_policy;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_cslp_signature_policy'
      AND parent_object_id = OBJECT_ID(N'dbo.client_supplier_label_profiles')
)
    ALTER TABLE dbo.client_supplier_label_profiles DROP CONSTRAINT CK_cslp_signature_policy;
GO

IF EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE name = N'DF_cslp_signature_policy'
      AND parent_object_id = OBJECT_ID(N'dbo.client_supplier_label_profiles')
)
    ALTER TABLE dbo.client_supplier_label_profiles DROP CONSTRAINT DF_cslp_signature_policy;
GO

IF COL_LENGTH(N'dbo.client_supplier_label_profiles', N'signature_policy') IS NOT NULL
    ALTER TABLE dbo.client_supplier_label_profiles DROP COLUMN signature_policy;
GO
