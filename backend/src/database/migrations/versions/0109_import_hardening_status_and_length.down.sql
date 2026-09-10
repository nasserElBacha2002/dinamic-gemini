/*
  Down 0109 — restore Phase-3-era import status checks and drop additive columns.
  Safe when no rows use MATERIALIZING / MATERIALIZATION_FAILED.
*/

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
      AND name = N'CK_local_csv_productive_results_position_code_len'
)
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT CK_local_csv_productive_results_position_code_len;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
      AND name = N'CK_local_csv_import_rows_position_code_len'
)
    ALTER TABLE dbo.local_csv_import_rows
        DROP CONSTRAINT CK_local_csv_import_rows_position_code_len;
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
            status IN (N'PREVIEWED', N'CONFIRMED')
        );
END;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
      AND name = N'CK_local_csv_imports_status'
)
    ALTER TABLE dbo.local_csv_imports DROP CONSTRAINT CK_local_csv_imports_status;
GO
ALTER TABLE dbo.local_csv_imports WITH CHECK
    ADD CONSTRAINT CK_local_csv_imports_status CHECK (
        status IN (N'PREVIEWED', N'CONFIRMED')
    );
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_attempts') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.default_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_imports')
          AND name = N'DF_local_csv_imports_materialization_attempts'
    )
        ALTER TABLE dbo.local_csv_imports
            DROP CONSTRAINT DF_local_csv_imports_materialization_attempts;
    ALTER TABLE dbo.local_csv_imports DROP COLUMN materialization_attempts;
END;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'last_error_code') IS NOT NULL
    ALTER TABLE dbo.local_csv_imports DROP COLUMN last_error_code;
GO
