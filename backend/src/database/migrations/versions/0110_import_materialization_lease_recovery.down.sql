/*
  Down 0110 — drop lease/recovery columns and restore 0109 status checks.
  Destructive for in-flight MATERIALIZING ownership metadata.
  REQUIRES_REVIEW rows must be resolved or remapped before down.
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.local_inventory_packages')
      AND name = N'IX_local_inventory_packages_recovery'
)
    DROP INDEX IX_local_inventory_packages_recovery ON dbo.local_inventory_packages;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_inventory_packages')
      AND name = N'CK_local_inventory_packages_lease_owner_pair'
)
    ALTER TABLE dbo.local_inventory_packages
        DROP CONSTRAINT CK_local_inventory_packages_lease_owner_pair;
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
    UPDATE dbo.local_inventory_packages
    SET status = N'MATERIALIZATION_FAILED'
    WHERE status = N'REQUIRES_REVIEW';

    ALTER TABLE dbo.local_inventory_packages WITH CHECK
        ADD CONSTRAINT CK_local_inventory_packages_status CHECK (
            status IN (
                N'PREVIEWED',
                N'MATERIALIZING',
                N'CONFIRMED',
                N'MATERIALIZATION_FAILED'
            )
        );
END;
GO

IF COL_LENGTH(N'dbo.local_inventory_packages', N'fencing_version') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.local_inventory_packages')
          AND name = N'DF_local_inventory_packages_fencing_version'
    )
        ALTER TABLE dbo.local_inventory_packages
            DROP CONSTRAINT DF_local_inventory_packages_fencing_version;
    ALTER TABLE dbo.local_inventory_packages DROP COLUMN fencing_version;
END;
GO
IF COL_LENGTH(N'dbo.local_inventory_packages', N'materialization_lease_expires_at') IS NOT NULL
    ALTER TABLE dbo.local_inventory_packages DROP COLUMN materialization_lease_expires_at;
GO
IF COL_LENGTH(N'dbo.local_inventory_packages', N'materialization_owner') IS NOT NULL
    ALTER TABLE dbo.local_inventory_packages DROP COLUMN materialization_owner;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'IX_local_csv_imports_recovery'
)
    DROP INDEX IX_local_csv_imports_recovery ON dbo.local_csv_imports;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_lease_owner_pair'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_lease_owner_pair;
GO
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_attempts_nonneg'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_attempts_nonneg;
GO
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_status'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_status;
GO

UPDATE dbo.local_csv_imports
SET status = N'MATERIALIZATION_FAILED'
WHERE status = N'REQUIRES_REVIEW';
GO

ALTER TABLE dbo.local_csv_imports WITH CHECK
    ADD CONSTRAINT CK_local_csv_imports_status CHECK (
        status IN (
            N'PREVIEWED',
            N'MATERIALIZING',
            N'CONFIRMED',
            N'MATERIALIZATION_FAILED'
        )
    );
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_next_retry_at') IS NOT NULL
    ALTER TABLE dbo.local_csv_imports DROP COLUMN materialization_next_retry_at;
GO
IF COL_LENGTH(N'dbo.local_csv_imports', N'fencing_version') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
          AND name = N'DF_local_csv_imports_fencing_version'
    )
        ALTER TABLE dbo.local_csv_imports
            DROP CONSTRAINT DF_local_csv_imports_fencing_version;
    ALTER TABLE dbo.local_csv_imports DROP COLUMN fencing_version;
END;
GO
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_last_attempt_at') IS NOT NULL
    ALTER TABLE dbo.local_csv_imports DROP COLUMN materialization_last_attempt_at;
GO
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_started_at') IS NOT NULL
    ALTER TABLE dbo.local_csv_imports DROP COLUMN materialization_started_at;
GO
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_lease_expires_at') IS NOT NULL
    ALTER TABLE dbo.local_csv_imports DROP COLUMN materialization_lease_expires_at;
GO
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_owner') IS NOT NULL
    ALTER TABLE dbo.local_csv_imports DROP COLUMN materialization_owner;
GO
