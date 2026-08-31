-- Formal rollback for 0100_label_recognition_profiles_phase1.sql (best-effort).

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_aisles_position_profile_source_override'
      AND parent_object_id = OBJECT_ID('aisles')
)
    ALTER TABLE aisles DROP CONSTRAINT CK_aisles_position_profile_source_override;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = 'CK_aisles_item_profile_source_override'
      AND parent_object_id = OBJECT_ID('aisles')
)
    ALTER TABLE aisles DROP CONSTRAINT CK_aisles_item_profile_source_override;
GO

IF COL_LENGTH('aisles', 'position_profile_source_override') IS NOT NULL
    ALTER TABLE aisles DROP COLUMN position_profile_source_override;
GO

IF COL_LENGTH('aisles', 'item_profile_source_override') IS NOT NULL
    ALTER TABLE aisles DROP COLUMN item_profile_source_override;
GO

IF OBJECT_ID('client_supplier_label_profiles', 'U') IS NOT NULL
    DROP TABLE client_supplier_label_profiles;
GO

IF COL_LENGTH('supplier_reference_images', 'label_kind') IS NOT NULL
    ALTER TABLE supplier_reference_images DROP COLUMN label_kind;
GO

IF COL_LENGTH('supplier_prompt_configs', 'label_kind') IS NOT NULL
    ALTER TABLE supplier_prompt_configs DROP COLUMN label_kind;
GO

IF COL_LENGTH('supplier_extraction_profiles', 'label_kind') IS NOT NULL
    ALTER TABLE supplier_extraction_profiles DROP COLUMN label_kind;
GO
