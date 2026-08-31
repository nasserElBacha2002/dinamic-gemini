-- Rollback 0101 — restores pre-label_kind unique indexes (POSITION rows may conflict if present).

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_supplier_prompt_configs_one_active_per_kind'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    DROP INDEX UQ_supplier_prompt_configs_one_active_per_kind ON supplier_prompt_configs;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_supplier_prompt_configs_scope_kind_version'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    DROP INDEX UQ_supplier_prompt_configs_scope_kind_version ON supplier_prompt_configs;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_supplier_prompt_configs_scope_version'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        CREATE UNIQUE INDEX UQ_supplier_prompt_configs_scope_version
            ON supplier_prompt_configs(
                client_supplier_id,
                provider_scope_key,
                model_scope_key,
                version
            );

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_supplier_prompt_configs_one_active'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        CREATE UNIQUE INDEX UQ_supplier_prompt_configs_one_active
            ON supplier_prompt_configs(
                client_supplier_id,
                provider_scope_key,
                model_scope_key
            )
            WHERE is_active = 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_one_active_per_kind'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    DROP INDEX UQ_sep_one_active_per_kind ON supplier_extraction_profiles;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_client_supplier_kind_version'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    DROP INDEX UQ_sep_client_supplier_kind_version ON supplier_extraction_profiles;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_client_supplier_version'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_sep_client_supplier_version
        ON supplier_extraction_profiles(client_id, supplier_id, version);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_one_active'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_sep_one_active
        ON supplier_extraction_profiles(client_id, supplier_id)
        WHERE status = 'ACTIVE';
GO
