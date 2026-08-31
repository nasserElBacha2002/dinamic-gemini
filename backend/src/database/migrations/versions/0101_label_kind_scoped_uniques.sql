-- Phase 1 correction — scope extraction/prompt uniqueness by label_kind (ITEM/POSITION independent).
-- Idempotent. Safe when 0100 backfilled legacy rows to ITEM.

-- Extraction profiles: version and ACTIVE uniqueness per label_kind.
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_one_active'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    DROP INDEX UQ_sep_one_active ON supplier_extraction_profiles;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_client_supplier_version'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    DROP INDEX UQ_sep_client_supplier_version ON supplier_extraction_profiles;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_client_supplier_kind_version'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_sep_client_supplier_kind_version
        ON supplier_extraction_profiles(client_id, supplier_id, label_kind, version);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'UQ_sep_one_active_per_kind'
      AND object_id = OBJECT_ID('supplier_extraction_profiles')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_sep_one_active_per_kind
        ON supplier_extraction_profiles(client_id, supplier_id, label_kind)
        WHERE status = 'ACTIVE';
GO

-- Prompt configs: version and ACTIVE uniqueness include label_kind within provider/model scope.
IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_supplier_prompt_configs_one_active'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        DROP INDEX UQ_supplier_prompt_configs_one_active ON supplier_prompt_configs;

    IF EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_supplier_prompt_configs_scope_version'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        DROP INDEX UQ_supplier_prompt_configs_scope_version ON supplier_prompt_configs;
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_supplier_prompt_configs_scope_kind_version'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        CREATE UNIQUE INDEX UQ_supplier_prompt_configs_scope_kind_version
            ON supplier_prompt_configs(
                client_supplier_id,
                provider_scope_key,
                model_scope_key,
                label_kind,
                version
            );

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_supplier_prompt_configs_one_active_per_kind'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        CREATE UNIQUE INDEX UQ_supplier_prompt_configs_one_active_per_kind
            ON supplier_prompt_configs(
                client_supplier_id,
                provider_scope_key,
                model_scope_key,
                label_kind
            )
            WHERE is_active = 1;
END;
GO
