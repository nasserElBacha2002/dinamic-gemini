-- Phase D1 — supplier prompt configs persistence foundation (additive only).
-- model_scope_key normalizes NULL model_name to a deterministic provider-default sentinel.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'supplier_prompt_configs')
BEGIN
    CREATE TABLE supplier_prompt_configs (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        client_supplier_id VARCHAR(36) NOT NULL,
        provider_name VARCHAR(32) NOT NULL,
        model_name VARCHAR(128) NULL,
        model_scope_key AS (CASE WHEN model_name IS NULL THEN '#NULL#' ELSE 'M:' + model_name END) PERSISTED,
        instructions_text NVARCHAR(MAX) NOT NULL,
        version INT NOT NULL,
        is_active BIT NOT NULL CONSTRAINT DF_supplier_prompt_configs_is_active DEFAULT (0),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_supplier_prompt_configs_client_supplier
            FOREIGN KEY (client_supplier_id) REFERENCES client_suppliers(id)
    );
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_supplier_prompt_configs_supplier_scope'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    CREATE INDEX IX_supplier_prompt_configs_supplier_scope
        ON supplier_prompt_configs(client_supplier_id, provider_name, model_name, created_at DESC);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_supplier_prompt_configs_scope_version'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_supplier_prompt_configs_scope_version
        ON supplier_prompt_configs(client_supplier_id, provider_name, model_scope_key, version);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_supplier_prompt_configs_one_active'
      AND object_id = OBJECT_ID('supplier_prompt_configs')
)
    CREATE UNIQUE INDEX UQ_supplier_prompt_configs_one_active
        ON supplier_prompt_configs(client_supplier_id, provider_name, model_scope_key)
        WHERE is_active = 1;
GO
