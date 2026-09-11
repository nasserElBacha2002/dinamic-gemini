/*
  Version 0110 — Phase 4 corrections: import materialization lease / recovery.
  Additive on top of 0109. Safe to re-run. Does not rewrite 0109.
*/

/* --- CSV import lease / fencing columns --- */
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_owner') IS NULL
    ALTER TABLE dbo.local_csv_imports ADD materialization_owner NVARCHAR(128) NULL;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_lease_expires_at') IS NULL
    ALTER TABLE dbo.local_csv_imports ADD materialization_lease_expires_at DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_started_at') IS NULL
    ALTER TABLE dbo.local_csv_imports ADD materialization_started_at DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_last_attempt_at') IS NULL
    ALTER TABLE dbo.local_csv_imports ADD materialization_last_attempt_at DATETIME2 NULL;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'fencing_version') IS NULL
    ALTER TABLE dbo.local_csv_imports
        ADD fencing_version INT NOT NULL
            CONSTRAINT DF_local_csv_imports_fencing_version DEFAULT 0;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_next_retry_at') IS NULL
    ALTER TABLE dbo.local_csv_imports ADD materialization_next_retry_at DATETIME2 NULL;
GO

/* Expand statuses with REQUIRES_REVIEW */
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_status'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_status;
GO
ALTER TABLE dbo.local_csv_imports WITH CHECK
    ADD CONSTRAINT CK_local_csv_imports_status CHECK (
        status IN (
            N'PREVIEWED',
            N'MATERIALIZING',
            N'CONFIRMED',
            N'MATERIALIZATION_FAILED',
            N'REQUIRES_REVIEW'
        )
    );
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_attempts_nonneg'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_attempts_nonneg;
GO
ALTER TABLE dbo.local_csv_imports WITH CHECK
    ADD CONSTRAINT CK_local_csv_imports_attempts_nonneg CHECK (
        materialization_attempts >= 0
    );
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_lease_owner_pair'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_lease_owner_pair;
GO
ALTER TABLE dbo.local_csv_imports WITH CHECK
    ADD CONSTRAINT CK_local_csv_imports_lease_owner_pair CHECK (
        (materialization_owner IS NULL AND materialization_lease_expires_at IS NULL)
        OR (materialization_owner IS NOT NULL AND materialization_lease_expires_at IS NOT NULL)
    );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'IX_local_csv_imports_recovery'
)
    CREATE NONCLUSTERED INDEX IX_local_csv_imports_recovery
        ON dbo.local_csv_imports(status, materialization_lease_expires_at, materialization_next_retry_at)
        WHERE status IN (N'MATERIALIZING', N'MATERIALIZATION_FAILED');
GO

/* --- Package lease columns (same workflow) --- */
IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NOT NULL
BEGIN
    IF COL_LENGTH(N'dbo.local_inventory_packages', N'materialization_owner') IS NULL
        ALTER TABLE dbo.local_inventory_packages ADD materialization_owner NVARCHAR(128) NULL;
    IF COL_LENGTH(N'dbo.local_inventory_packages', N'materialization_lease_expires_at') IS NULL
        ALTER TABLE dbo.local_inventory_packages ADD materialization_lease_expires_at DATETIME2 NULL;
    IF COL_LENGTH(N'dbo.local_inventory_packages', N'fencing_version') IS NULL
        ALTER TABLE dbo.local_inventory_packages
            ADD fencing_version INT NOT NULL
                CONSTRAINT DF_local_inventory_packages_fencing_version DEFAULT 0;
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_inventory_packages')
      AND name = N'CK_local_inventory_packages_status'
)
    ALTER TABLE dbo.local_inventory_packages
        DROP CONSTRAINT CK_local_inventory_packages_status;
GO
IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_inventory_packages WITH CHECK
        ADD CONSTRAINT CK_local_inventory_packages_status CHECK (
            status IN (
                N'PREVIEWED',
                N'MATERIALIZING',
                N'CONFIRMED',
                N'MATERIALIZATION_FAILED',
                N'REQUIRES_REVIEW'
            )
        );
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_inventory_packages')
      AND name = N'CK_local_inventory_packages_lease_owner_pair'
)
    ALTER TABLE dbo.local_inventory_packages
        DROP CONSTRAINT CK_local_inventory_packages_lease_owner_pair;
GO
IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_inventory_packages WITH CHECK
        ADD CONSTRAINT CK_local_inventory_packages_lease_owner_pair CHECK (
            (materialization_owner IS NULL AND materialization_lease_expires_at IS NULL)
            OR (materialization_owner IS NOT NULL AND materialization_lease_expires_at IS NOT NULL)
        );
END;
GO

IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.local_inventory_packages')
      AND name = N'IX_local_inventory_packages_recovery'
)
    CREATE NONCLUSTERED INDEX IX_local_inventory_packages_recovery
        ON dbo.local_inventory_packages(status, materialization_lease_expires_at)
        WHERE status IN (N'MATERIALIZING', N'MATERIALIZATION_FAILED');
GO
