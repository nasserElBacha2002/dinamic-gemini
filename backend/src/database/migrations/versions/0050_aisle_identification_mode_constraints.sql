-- Phase 1 corrections — CHECK constraints for aisle identification mode fields.
-- Idempotent. Fails clearly if invalid non-null data exists (no silent coerce).
-- Keep aligned with backend/src/database/schema.sql.

-- Guard: reject unknown persisted values before adding constraints.
IF EXISTS (
    SELECT 1 FROM clients
    WHERE default_identification_mode IS NOT NULL
      AND default_identification_mode NOT IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
)
BEGIN
    THROW 50049, 'Invalid clients.default_identification_mode values found; fix data before 0050 constraints.', 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM inventories
    WHERE identification_mode IS NOT NULL
      AND identification_mode NOT IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
)
BEGIN
    THROW 50050, 'Invalid inventories.identification_mode values found; fix data before 0050 constraints.', 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM aisles
    WHERE identification_mode IS NOT NULL
      AND identification_mode NOT IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
)
BEGIN
    THROW 50051, 'Invalid aisles.identification_mode values found; fix data before 0050 constraints.', 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE identification_mode NOT IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
)
BEGIN
    THROW 50052, 'Invalid inventory_jobs.identification_mode values found; fix data before 0050 constraints.', 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE identification_mode_source NOT IN (
        'REQUEST', 'AISLE', 'INVENTORY', 'CLIENT', 'SYSTEM_DEFAULT', 'LEGACY_MIGRATION'
    )
)
BEGIN
    THROW 50053, 'Invalid inventory_jobs.identification_mode_source values found; fix data before 0050 constraints.', 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE execution_strategy NOT IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY')
)
BEGIN
    THROW 50054, 'Invalid inventory_jobs.execution_strategy values found; fix data before 0050 constraints.', 1;
END;
GO

IF EXISTS (
    SELECT 1 FROM inventory_jobs
    WHERE configuration_snapshot_version IS NULL OR configuration_snapshot_version <= 0
)
BEGIN
    THROW 50055, 'Invalid inventory_jobs.configuration_snapshot_version values found; fix data before 0050 constraints.', 1;
END;
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_clients_default_identification_mode'
)
    ALTER TABLE clients ADD CONSTRAINT CK_clients_default_identification_mode
    CHECK (
        default_identification_mode IS NULL
        OR default_identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
    );
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_inventories_identification_mode'
)
    ALTER TABLE inventories ADD CONSTRAINT CK_inventories_identification_mode
    CHECK (
        identification_mode IS NULL
        OR identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
    );
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_aisles_identification_mode'
)
    ALTER TABLE aisles ADD CONSTRAINT CK_aisles_identification_mode
    CHECK (
        identification_mode IS NULL
        OR identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM')
    );
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_identification_mode'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_identification_mode
    CHECK (identification_mode IN ('CODE_SCAN', 'INTERNAL_OCR', 'LEGACY_LLM'));
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_identification_mode_source'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_identification_mode_source
    CHECK (
        identification_mode_source IN (
            'REQUEST', 'AISLE', 'INVENTORY', 'CLIENT', 'SYSTEM_DEFAULT', 'LEGACY_MIGRATION'
        )
    );
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_execution_strategy'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_execution_strategy
    CHECK (execution_strategy IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY'));
GO

IF NOT EXISTS (
    SELECT * FROM sys.check_constraints WHERE name = 'CK_inventory_jobs_configuration_snapshot_version'
)
    ALTER TABLE inventory_jobs ADD CONSTRAINT CK_inventory_jobs_configuration_snapshot_version
    CHECK (configuration_snapshot_version > 0);
GO
