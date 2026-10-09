/*
  Fail-closed preflight for Phase 5 flexible position (migration 0111+).

  Verifies:
  - required tables/columns for signature_policy and position_flexible_capabilities
  - signature_policy backfill completeness and allowed values
  - UQ_pfc_scope_key unique index
  - UQ_aisle_locations_client_aisle_normalized_code_active (definition + enabled)
  - active duplicate aisle_locations under the identity key
  - position_materialization_requests table presence (Phase 3 ledger)
  - association receipt/recovery columns when the ledger exists
  - incoherent enabled ENFORCED capabilities without channel name validity

  Any failure → THROW 51011. Comment must match checks below.
*/

SET NOCOUNT ON;

DECLARE @errors TABLE (code NVARCHAR(64) NOT NULL, detail NVARCHAR(400) NOT NULL);

/* --- 0111 columns --- */
IF OBJECT_ID(N'dbo.client_supplier_label_profiles', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'client_supplier_label_profiles');
ELSE IF COL_LENGTH(N'dbo.client_supplier_label_profiles', N'signature_policy') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'client_supplier_label_profiles.signature_policy');

IF OBJECT_ID(N'dbo.supplier_extraction_profiles', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'supplier_extraction_profiles');
ELSE IF COL_LENGTH(N'dbo.supplier_extraction_profiles', N'signature_policy') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'supplier_extraction_profiles.signature_policy');

IF OBJECT_ID(N'dbo.position_flexible_capabilities', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'position_flexible_capabilities');
ELSE
BEGIN
    IF COL_LENGTH(N'dbo.position_flexible_capabilities', N'client_id') IS NULL
        INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'position_flexible_capabilities.client_id');
    IF COL_LENGTH(N'dbo.position_flexible_capabilities', N'channel') IS NULL
        INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'position_flexible_capabilities.channel');
    IF COL_LENGTH(N'dbo.position_flexible_capabilities', N'mode') IS NULL
        INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'position_flexible_capabilities.mode');
    IF COL_LENGTH(N'dbo.position_flexible_capabilities', N'enabled') IS NULL
        INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'position_flexible_capabilities.enabled');
    IF COL_LENGTH(N'dbo.position_flexible_capabilities', N'scope_key') IS NULL
        INSERT INTO @errors VALUES (N'MISSING_COLUMN', N'position_flexible_capabilities.scope_key');
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.position_flexible_capabilities')
          AND name = N'UQ_pfc_scope_key'
          AND is_unique = 1
          AND is_disabled = 0
    )
        INSERT INTO @errors VALUES (N'MISSING_INDEX', N'UQ_pfc_scope_key');

    /* Incoherent enabled rows */
    IF EXISTS (
        SELECT 1 FROM dbo.position_flexible_capabilities
        WHERE enabled = 1
          AND (
                channel NOT IN (N'CODE_SCAN', N'VISION', N'MOBILE', N'IMPORT', N'REVIEW')
             OR mode NOT IN (N'SHADOW', N'ENFORCED')
          )
    )
        INSERT INTO @errors VALUES (
            N'BAD_CAPABILITY_ROW',
            N'enabled capability with invalid channel/mode'
        );
END;

/* --- signature_policy backfill --- */
IF OBJECT_ID(N'dbo.client_supplier_label_profiles', N'U') IS NOT NULL
AND COL_LENGTH(N'dbo.client_supplier_label_profiles', N'signature_policy') IS NOT NULL
AND EXISTS (
    SELECT 1 FROM dbo.client_supplier_label_profiles
    WHERE signature_policy IS NULL
       OR LTRIM(RTRIM(signature_policy)) = N''
       OR signature_policy NOT IN (N'REQUIRED', N'OPTIONAL', N'NOT_APPLICABLE')
)
    INSERT INTO @errors VALUES (
        N'BAD_SIGNATURE_POLICY',
        N'client_supplier_label_profiles.signature_policy backfill incomplete'
    );

IF OBJECT_ID(N'dbo.supplier_extraction_profiles', N'U') IS NOT NULL
AND COL_LENGTH(N'dbo.supplier_extraction_profiles', N'signature_policy') IS NOT NULL
AND EXISTS (
    SELECT 1 FROM dbo.supplier_extraction_profiles
    WHERE signature_policy IS NULL
       OR LTRIM(RTRIM(signature_policy)) = N''
       OR signature_policy NOT IN (N'REQUIRED', N'OPTIONAL', N'NOT_APPLICABLE')
)
    INSERT INTO @errors VALUES (
        N'BAD_SIGNATURE_POLICY',
        N'supplier_extraction_profiles.signature_policy backfill incomplete'
    );

/* --- aisle_locations unique identity index (Phase 3 prerequisite) --- */
IF OBJECT_ID(N'dbo.aisle_locations', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'aisle_locations');
ELSE
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes i
        WHERE i.object_id = OBJECT_ID(N'dbo.aisle_locations')
          AND i.name = N'UQ_aisle_locations_client_aisle_normalized_code_active'
          AND i.is_unique = 1
          AND i.is_disabled = 0
          AND i.has_filter = 1
          AND REPLACE(UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
              i.filter_definition, N'[', N''), N']', N''), N'(', N''), N')', N''), N' ', N'')),
              N'=N''ACTIVE''', N'=''ACTIVE''')
              = N'STATUS=''ACTIVE'''
    )
        INSERT INTO @errors VALUES (
            N'MISSING_OR_MALFORMED_INDEX',
            N'UQ_aisle_locations_client_aisle_normalized_code_active'
        );

    /* Active duplicates under identity key */
    IF COL_LENGTH(N'dbo.aisle_locations', N'client_id') IS NOT NULL
    AND COL_LENGTH(N'dbo.aisle_locations', N'aisle_id') IS NOT NULL
    AND COL_LENGTH(N'dbo.aisle_locations', N'normalized_code') IS NOT NULL
    AND COL_LENGTH(N'dbo.aisle_locations', N'status') IS NOT NULL
    AND EXISTS (
        SELECT client_id, aisle_id, normalized_code
        FROM dbo.aisle_locations
        WHERE status = N'ACTIVE'
        GROUP BY client_id, aisle_id, normalized_code
        HAVING COUNT(*) > 1
    )
        INSERT INTO @errors VALUES (
            N'ACTIVE_DUPLICATES',
            N'aisle_locations active duplicates on (client_id, aisle_id, normalized_code)'
        );
END;

/* --- position materialization ledger + association recovery --- */
IF OBJECT_ID(N'dbo.position_materialization_requests', N'U') IS NULL
    INSERT INTO @errors VALUES (N'MISSING_TABLE', N'position_materialization_requests');
ELSE
BEGIN
    IF COL_LENGTH(N'dbo.position_materialization_requests', N'idempotency_key') IS NULL
        INSERT INTO @errors VALUES (
            N'MISSING_COLUMN',
            N'position_materialization_requests.idempotency_key'
        );
    IF COL_LENGTH(N'dbo.position_materialization_requests', N'association_status') IS NULL
        INSERT INTO @errors VALUES (
            N'MISSING_COLUMN',
            N'position_materialization_requests.association_status'
        );
END;

IF OBJECT_ID(N'dbo.position_materialization_association_receipts', N'U') IS NULL
    INSERT INTO @errors VALUES (
        N'MISSING_TABLE',
        N'position_materialization_association_receipts'
    );

/* Diagnostics */
SELECT N'client_supplier_label_profiles.signature_policy' AS check_name,
       COL_LENGTH(N'dbo.client_supplier_label_profiles', N'signature_policy') AS col_length;

SELECT N'position_flexible_capabilities' AS check_name,
       OBJECT_ID(N'dbo.position_flexible_capabilities', N'U') AS object_id;

SELECT code, detail FROM @errors ORDER BY code, detail;

IF EXISTS (SELECT 1 FROM @errors)
BEGIN
    DECLARE @msg NVARCHAR(2048) =
        (SELECT STRING_AGG(CONCAT(code, N': ', detail), N'; ') FROM @errors);
    THROW 51011, @msg, 1;
END;

SET NOCOUNT OFF;
