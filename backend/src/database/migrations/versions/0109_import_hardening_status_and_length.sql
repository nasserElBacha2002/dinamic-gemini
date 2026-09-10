/*
  Version 0109 — Phase 4 import hardening:
  - Expand local_csv_imports / local_inventory_packages status machine
  - Track materialization attempts / last_error_code
  - Enforce canonical position code length (64) on import staging rows
*/

/* --- local_csv_imports status + recovery columns --- */
IF COL_LENGTH(N'dbo.local_csv_imports', N'last_error_code') IS NULL
    ALTER TABLE dbo.local_csv_imports ADD last_error_code NVARCHAR(64) NULL;
GO

IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_attempts') IS NULL
    ALTER TABLE dbo.local_csv_imports
        ADD materialization_attempts INT NOT NULL
            CONSTRAINT DF_local_csv_imports_materialization_attempts DEFAULT 0;
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
        status IN (
            N'PREVIEWED',
            N'MATERIALIZING',
            N'CONFIRMED',
            N'MATERIALIZATION_FAILED'
        )
    );
GO

/* --- package statuses align with import materialization workflow --- */
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
                N'MATERIALIZATION_FAILED'
            )
        );
END;
GO

/* --- Canonical length on non-empty import position codes (no silent truncate) --- */
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_import_rows')
      AND name = N'CK_local_csv_import_rows_position_code_len'
)
    ALTER TABLE dbo.local_csv_import_rows
        DROP CONSTRAINT CK_local_csv_import_rows_position_code_len;
GO
ALTER TABLE dbo.local_csv_import_rows WITH CHECK
    ADD CONSTRAINT CK_local_csv_import_rows_position_code_len CHECK (
        LEN(LTRIM(RTRIM(position_code))) = 0
        OR LEN(position_code) <= 64
    );
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.local_csv_productive_results')
      AND name = N'CK_local_csv_productive_results_position_code_len'
)
    ALTER TABLE dbo.local_csv_productive_results
        DROP CONSTRAINT CK_local_csv_productive_results_position_code_len;
GO
IF COL_LENGTH(N'dbo.local_csv_productive_results', N'position_code') IS NOT NULL
BEGIN
    ALTER TABLE dbo.local_csv_productive_results WITH CHECK
        ADD CONSTRAINT CK_local_csv_productive_results_position_code_len CHECK (
            position_code IS NULL
            OR LEN(LTRIM(RTRIM(position_code))) = 0
            OR LEN(position_code) <= 64
        );
END;
GO
