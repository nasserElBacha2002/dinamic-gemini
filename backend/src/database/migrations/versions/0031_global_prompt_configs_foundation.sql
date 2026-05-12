-- Phase D9 — global prompt configs persistence foundation (additive only).
-- model_scope_key normalizes NULL model_name to a deterministic scope sentinel.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'global_prompt_configs')
BEGIN
    CREATE TABLE global_prompt_configs (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        scope_type VARCHAR(32) NOT NULL CONSTRAINT DF_global_prompt_configs_scope_type DEFAULT ('global'),
        provider_name VARCHAR(32) NULL,
        model_name VARCHAR(128) NULL,
        model_scope_key AS (CASE WHEN model_name IS NULL THEN '#NULL#' ELSE 'M:' + model_name END) PERSISTED,
        instructions_text NVARCHAR(MAX) NOT NULL,
        version INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_global_prompt_configs_is_active DEFAULT (0),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT CK_global_prompt_configs_scope_type_global
            CHECK (scope_type = 'global'),
        CONSTRAINT CK_global_prompt_configs_global_null_provider_model
            CHECK (scope_type <> 'global' OR (provider_name IS NULL AND model_name IS NULL))
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_global_prompt_configs_scope'
      AND object_id = OBJECT_ID('global_prompt_configs')
)
    CREATE INDEX IX_global_prompt_configs_scope
        ON global_prompt_configs(scope_type, provider_name, model_name, created_at DESC);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_global_prompt_configs_scope_version'
      AND object_id = OBJECT_ID('global_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_global_prompt_configs_scope_version
        ON global_prompt_configs(scope_type, provider_name, model_scope_key, version);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_global_prompt_configs_one_active'
      AND object_id = OBJECT_ID('global_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_global_prompt_configs_one_active
        ON global_prompt_configs(scope_type, provider_name, model_scope_key)
        WHERE is_active = 1;
GO
