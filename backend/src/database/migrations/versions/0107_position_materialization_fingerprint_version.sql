/*
  Version 0107 — persist the semantic fingerprint format version.

  0105 and 0106 may already be applied, so this correction is strictly additive.
  Existing request hashes were all produced by FingerprintV1 and are backfilled as V1.
*/

IF COL_LENGTH(
    N'dbo.position_materialization_requests',
    N'fingerprint_version'
) IS NULL
    ALTER TABLE dbo.position_materialization_requests
        ADD fingerprint_version INT NOT NULL
            CONSTRAINT DF_pmr_fingerprint_version DEFAULT (1) WITH VALUES;
GO

IF EXISTS (
    SELECT 1 FROM dbo.position_materialization_requests
    WHERE fingerprint_version <> 1
)
    THROW 51017, 'Unsupported materialization fingerprint versions detected', 1;
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

ALTER TABLE dbo.position_materialization_requests
    ALTER COLUMN fingerprint_version INT NOT NULL;
GO

ALTER TABLE dbo.position_materialization_requests
    ADD CONSTRAINT DF_pmr_fingerprint_version
        DEFAULT (1) FOR fingerprint_version;
GO

ALTER TABLE dbo.position_materialization_requests WITH CHECK
    ADD CONSTRAINT CK_pmr_fingerprint_version
        CHECK (fingerprint_version = 1);
GO

ALTER TABLE dbo.position_materialization_requests
    CHECK CONSTRAINT CK_pmr_fingerprint_version;
GO
