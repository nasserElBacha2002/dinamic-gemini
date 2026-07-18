-- Phase 1 — Aisle identification mode (hierarchical config + immutable job snapshot).
-- Additive only. Independent of inventories.processing_mode (production|test).
-- Historical jobs backfilled to LEGACY_LLM / LEGACY_MIGRATION.
-- Keep aligned with backend/src/database/schema.sql.

-- Client default (nullable = inherit system default LEGACY_LLM)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('clients') AND name = 'default_identification_mode')
    ALTER TABLE clients ADD default_identification_mode VARCHAR(32) NULL;
GO

-- Inventory override (nullable = inherit client/system)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'identification_mode')
    ALTER TABLE inventories ADD identification_mode VARCHAR(32) NULL;
GO

-- Aisle override (nullable = inherit inventory/client/system)
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'identification_mode')
    ALTER TABLE aisles ADD identification_mode VARCHAR(32) NULL;
GO

-- Job immutable snapshot columns
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'identification_mode')
    ALTER TABLE inventory_jobs ADD identification_mode VARCHAR(32) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'identification_mode_source')
    ALTER TABLE inventory_jobs ADD identification_mode_source VARCHAR(32) NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'configuration_snapshot_version')
    ALTER TABLE inventory_jobs ADD configuration_snapshot_version INT NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventory_jobs') AND name = 'execution_strategy')
    ALTER TABLE inventory_jobs ADD execution_strategy VARCHAR(64) NULL;
GO

-- Backfill historical jobs for safe reads
UPDATE inventory_jobs
SET identification_mode = 'LEGACY_LLM'
WHERE identification_mode IS NULL;
GO

UPDATE inventory_jobs
SET identification_mode_source = 'LEGACY_MIGRATION'
WHERE identification_mode_source IS NULL;
GO

UPDATE inventory_jobs
SET configuration_snapshot_version = 1
WHERE configuration_snapshot_version IS NULL;
GO

UPDATE inventory_jobs
SET execution_strategy = 'LEGACY_LLM'
WHERE execution_strategy IS NULL;
GO

-- Enforce NOT NULL on job identification_mode after backfill
IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('inventory_jobs')
      AND name = 'identification_mode'
      AND is_nullable = 1
)
    ALTER TABLE inventory_jobs ALTER COLUMN identification_mode VARCHAR(32) NOT NULL;
GO

IF EXISTS (
    SELECT * FROM sys.columns
    WHERE object_id = OBJECT_ID('inventory_jobs')
      AND name = 'identification_mode_source'
      AND is_nullable = 1
)
    ALTER TABLE inventory_jobs ALTER COLUMN identification_mode_source VARCHAR(32) NOT NULL;
GO

IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('inventory_jobs')
      AND name = 'DF_inventory_jobs_identification_mode'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_identification_mode
        DEFAULT ('LEGACY_LLM') FOR identification_mode;
GO

IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('inventory_jobs')
      AND name = 'DF_inventory_jobs_identification_mode_source'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_identification_mode_source
        DEFAULT ('LEGACY_MIGRATION') FOR identification_mode_source;
GO

IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('inventory_jobs')
      AND name = 'DF_inventory_jobs_configuration_snapshot_version'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_configuration_snapshot_version
        DEFAULT (1) FOR configuration_snapshot_version;
GO

IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('inventory_jobs')
      AND name = 'DF_inventory_jobs_execution_strategy'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT DF_inventory_jobs_execution_strategy
        DEFAULT ('LEGACY_LLM') FOR execution_strategy;
GO
