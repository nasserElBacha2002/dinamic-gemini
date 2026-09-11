/*
  Fail-closed preflight for Phase 4 import hardening (0109 + 0110).
  Exits with THROW when the database is unsafe for the new import workflow.
*/

SET NOCOUNT ON;

DECLARE @errors TABLE (code NVARCHAR(64) NOT NULL, detail NVARCHAR(400) NOT NULL);

IF OBJECT_ID(N'dbo.local_csv_imports', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'local_csv_imports');
IF OBJECT_ID(N'dbo.local_csv_import_rows', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'local_csv_import_rows');
IF OBJECT_ID(N'dbo.local_csv_productive_results', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'local_csv_productive_results');

IF COL_LENGTH(N'dbo.local_csv_imports', N'last_error_code') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'local_csv_imports.last_error_code');
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_attempts') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'local_csv_imports.materialization_attempts');
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_owner') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'local_csv_imports.materialization_owner');
IF COL_LENGTH(N'dbo.local_csv_imports', N'materialization_lease_expires_at') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'local_csv_imports.materialization_lease_expires_at');
IF COL_LENGTH(N'dbo.local_csv_imports', N'fencing_version') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'local_csv_imports.fencing_version');

IF EXISTS (
    SELECT 1 FROM dbo.local_csv_imports
    WHERE status NOT IN (
        N'PREVIEWED', N'MATERIALIZING', N'CONFIRMED',
        N'MATERIALIZATION_FAILED', N'REQUIRES_REVIEW'
    )
)
    INSERT INTO @errors VALUES (N'UNKNOWN_STATUS', N'local_csv_imports has unrecognized status');

IF EXISTS (
    SELECT 1 FROM dbo.local_csv_import_rows
    WHERE LEN(LTRIM(RTRIM(position_code))) > 0 AND LEN(position_code) > 64
)
    INSERT INTO @errors VALUES (N'OVERSIZE_POSITION_CODE', N'local_csv_import_rows.position_code > 64');

IF EXISTS (
    SELECT 1 FROM dbo.local_csv_productive_results
    WHERE position_code IS NOT NULL
      AND LEN(LTRIM(RTRIM(position_code))) > 0
      AND LEN(position_code) > 64
)
    INSERT INTO @errors VALUES (N'OVERSIZE_POSITION_CODE', N'local_csv_productive_results.position_code > 64');

IF OBJECT_ID(N'dbo.local_inventory_packages', N'U') IS NOT NULL
AND EXISTS (
    SELECT 1
    FROM dbo.local_inventory_packages p
    INNER JOIN dbo.local_csv_imports i ON i.id = p.csv_import_id
    WHERE (p.status = N'CONFIRMED' AND i.status <> N'CONFIRMED')
       OR (i.status = N'CONFIRMED' AND p.status <> N'CONFIRMED')
)
    INSERT INTO @errors VALUES (
        N'PACKAGE_CSV_INCONSISTENT',
        N'package/CSV confirmation status mismatch'
    );

IF EXISTS (
    SELECT 1 FROM dbo.local_csv_imports
    WHERE status = N'MATERIALIZING'
      AND materialization_lease_expires_at IS NULL
)
    INSERT INTO @errors VALUES (
        N'MATERIALIZING_WITHOUT_LEASE',
        N'MATERIALIZING rows lack lease metadata; apply 0110 before recovery'
    );

-- Diagnostics (always returned)
SELECT status, COUNT(*) AS row_count
FROM dbo.local_csv_imports
GROUP BY status;

SELECT code, detail FROM @errors ORDER BY code, detail;

IF EXISTS (SELECT 1 FROM @errors)
BEGIN
    DECLARE @msg NVARCHAR(2048) =
        (SELECT STRING_AGG(CONCAT(code, N': ', detail), N'; ') FROM @errors);
    THROW 51009, @msg, 1;
END;

-- Restore rowcounts for pooled ODBC sessions (avoids pyodbc rowcount=-1 after NOCOUNT).
SET NOCOUNT OFF;
