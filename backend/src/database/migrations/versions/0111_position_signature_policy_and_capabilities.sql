/*
  Phase 5 — position signature_policy on label profiles + flexible capabilities registry.
  Additive / idempotent. Does not enable GLOBAL_ROLLOUT.
*/

/* -------------------------------------------------------------------------- */
/* client_supplier_label_profiles.signature_policy                            */
/* -------------------------------------------------------------------------- */

IF COL_LENGTH(N'dbo.client_supplier_label_profiles', N'signature_policy') IS NULL
BEGIN
    ALTER TABLE dbo.client_supplier_label_profiles
        ADD signature_policy NVARCHAR(32) NOT NULL
            CONSTRAINT DF_cslp_signature_policy DEFAULT (N'REQUIRED');
END;
GO

UPDATE dbo.client_supplier_label_profiles
SET signature_policy = N'REQUIRED'
WHERE signature_policy IS NULL
   OR LTRIM(RTRIM(signature_policy)) = N'';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_cslp_signature_policy'
      AND parent_object_id = OBJECT_ID(N'dbo.client_supplier_label_profiles')
)
BEGIN
    ALTER TABLE dbo.client_supplier_label_profiles
        ADD CONSTRAINT CK_cslp_signature_policy
            CHECK (signature_policy IN (N'REQUIRED', N'OPTIONAL', N'NOT_APPLICABLE'));
END;
GO

/* -------------------------------------------------------------------------- */
/* supplier_extraction_profiles.signature_policy (POSITION rows)              */
/* -------------------------------------------------------------------------- */

IF COL_LENGTH(N'dbo.supplier_extraction_profiles', N'signature_policy') IS NULL
BEGIN
    ALTER TABLE dbo.supplier_extraction_profiles
        ADD signature_policy NVARCHAR(32) NOT NULL
            CONSTRAINT DF_sep_signature_policy DEFAULT (N'REQUIRED');
END;
GO

UPDATE dbo.supplier_extraction_profiles
SET signature_policy = N'REQUIRED'
WHERE signature_policy IS NULL
   OR LTRIM(RTRIM(signature_policy)) = N'';
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE name = N'CK_sep_signature_policy'
      AND parent_object_id = OBJECT_ID(N'dbo.supplier_extraction_profiles')
)
BEGIN
    ALTER TABLE dbo.supplier_extraction_profiles
        ADD CONSTRAINT CK_sep_signature_policy
            CHECK (signature_policy IN (N'REQUIRED', N'OPTIONAL', N'NOT_APPLICABLE'));
END;
GO

/* -------------------------------------------------------------------------- */
/* position_flexible_capabilities                                             */
/* -------------------------------------------------------------------------- */

IF OBJECT_ID(N'dbo.position_flexible_capabilities', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.position_flexible_capabilities (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        client_supplier_id VARCHAR(36) NULL,
        profile_id VARCHAR(36) NULL,
        channel NVARCHAR(32) NOT NULL,
        mode NVARCHAR(16) NOT NULL,
        enabled BIT NOT NULL CONSTRAINT DF_pfc_enabled DEFAULT (0),
        reason NVARCHAR(256) NULL,
        created_by VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_position_flexible_capabilities PRIMARY KEY (id),
        CONSTRAINT CK_pfc_channel CHECK (
            channel IN (N'CODE_SCAN', N'VISION', N'MOBILE', N'IMPORT', N'REVIEW')
        ),
        CONSTRAINT CK_pfc_mode CHECK (mode IN (N'SHADOW', N'ENFORCED'))
    );

    IF OBJECT_ID(N'dbo.clients', N'U') IS NOT NULL
    BEGIN
        ALTER TABLE dbo.position_flexible_capabilities
            ADD CONSTRAINT FK_pfc_client
                FOREIGN KEY (client_id) REFERENCES dbo.clients(id);
    END
END;
GO

IF COL_LENGTH(N'dbo.position_flexible_capabilities', N'scope_key') IS NULL
BEGIN
    ALTER TABLE dbo.position_flexible_capabilities
        ADD scope_key AS (
            CONCAT(
                client_id, N'|', channel, N'|',
                ISNULL(client_supplier_id, N''), N'|',
                ISNULL(profile_id, N'')
            )
        ) PERSISTED;
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_pfc_scope_key'
      AND object_id = OBJECT_ID(N'dbo.position_flexible_capabilities')
)
BEGIN
    /* Logical unique on (client_id, channel, ISNULL(supplier,''), ISNULL(profile,'')) */
    CREATE UNIQUE NONCLUSTERED INDEX UQ_pfc_scope_key
        ON dbo.position_flexible_capabilities (scope_key);
END;
GO
