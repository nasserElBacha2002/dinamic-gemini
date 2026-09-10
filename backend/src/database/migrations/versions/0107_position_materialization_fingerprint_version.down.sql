/*
  Roll back persisted materialization fingerprint version metadata.
*/

IF EXISTS (
    SELECT 1 FROM dbo.position_materialization_requests
    WHERE fingerprint_version <> 1
)
    THROW 51018,
        '0107 rollback blocked by unsupported materialization fingerprint versions',
        1;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_fingerprint_version'
)
    ALTER TABLE dbo.position_materialization_requests
        DROP CONSTRAINT CK_pmr_fingerprint_version;
GO

IF EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'DF_pmr_fingerprint_version'
)
    ALTER TABLE dbo.position_materialization_requests
        DROP CONSTRAINT DF_pmr_fingerprint_version;
GO

IF COL_LENGTH(
    N'dbo.position_materialization_requests',
    N'fingerprint_version'
) IS NOT NULL
    ALTER TABLE dbo.position_materialization_requests
        DROP COLUMN fingerprint_version;
GO
