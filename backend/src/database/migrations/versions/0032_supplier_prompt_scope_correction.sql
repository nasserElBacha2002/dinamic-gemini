-- Phase D9 correction: remove mistaken system-wide global prompt config surface
-- and extend supplier_prompt_configs to support supplier-scoped all-providers/all-models.

-- 1) Remove wrong global table (feature is supplier-scoped only).
IF OBJECT_ID('global_prompt_configs', 'U') IS NOT NULL
BEGIN
    DROP TABLE global_prompt_configs;
END;
GO

-- 2) Extend supplier_prompt_configs scope keys and constraints.
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

    IF EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_supplier_prompt_configs_supplier_scope'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        DROP INDEX IX_supplier_prompt_configs_supplier_scope ON supplier_prompt_configs;
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1
        FROM sys.columns
        WHERE object_id = OBJECT_ID('supplier_prompt_configs')
          AND name = 'provider_name'
          AND is_nullable = 0
    )
        ALTER TABLE supplier_prompt_configs ALTER COLUMN provider_name VARCHAR(32) NULL;
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id = OBJECT_ID('supplier_prompt_configs')
          AND name = 'model_scope_key'
    )
        ALTER TABLE supplier_prompt_configs DROP COLUMN model_scope_key;

    ALTER TABLE supplier_prompt_configs
    ADD model_scope_key AS (
        CASE
            WHEN model_name IS NULL THEN '#ALL_MODELS#'
            ELSE 'M:' + model_name
        END
    ) PERSISTED;
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.columns
        WHERE object_id = OBJECT_ID('supplier_prompt_configs')
          AND name = 'provider_scope_key'
    )
        ALTER TABLE supplier_prompt_configs DROP COLUMN provider_scope_key;

    ALTER TABLE supplier_prompt_configs
    ADD provider_scope_key AS (
        CASE
            WHEN provider_name IS NULL THEN '#ALL_PROVIDERS#'
            ELSE 'P:' + LOWER(provider_name)
        END
    ) PERSISTED;
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = 'CK_supplier_prompt_configs_valid_scope'
          AND parent_object_id = OBJECT_ID('supplier_prompt_configs')
    )
        ALTER TABLE supplier_prompt_configs
        ADD CONSTRAINT CK_supplier_prompt_configs_valid_scope
        CHECK (NOT (provider_name IS NULL AND model_name IS NOT NULL));
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_supplier_prompt_configs_supplier_scope'
          AND object_id = OBJECT_ID('supplier_prompt_configs')
    )
        CREATE INDEX IX_supplier_prompt_configs_supplier_scope
            ON supplier_prompt_configs(
                client_supplier_id,
                provider_scope_key,
                model_scope_key,
                created_at DESC
            );
END;
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
END;
GO

IF OBJECT_ID('supplier_prompt_configs', 'U') IS NOT NULL
BEGIN
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
