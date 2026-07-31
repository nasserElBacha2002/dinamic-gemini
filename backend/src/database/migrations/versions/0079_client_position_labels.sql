/*
  0079_client_position_labels.sql

  Simplify positioning labels to client scope:
  - New dbo.client_position_labels (no inventory/aisle ownership)
  - New dbo.client_position_label_artifacts
  - Migrate labels from aisle_location_labels when present
  - Preserve public_identifier when possible

  Rollback: 0079_client_position_labels.down.sql
*/

-- ---------------------------------------------------------------------------
-- client_position_labels
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.client_position_labels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_position_labels (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        public_identifier VARCHAR(64) NOT NULL,
        name NVARCHAR(200) NOT NULL,
        normalized_name NVARCHAR(200) NOT NULL,
        description NVARCHAR(1000) NULL,
        status VARCHAR(32) NOT NULL
            CONSTRAINT DF_client_position_labels_status DEFAULT ('ACTIVE'),
        payload_version INT NOT NULL
            CONSTRAINT DF_client_position_labels_payload_version DEFAULT (1),
        canonical_payload NVARCHAR(MAX) NOT NULL,
        payload_hash VARCHAR(128) NULL,
        signature NVARCHAR(128) NULL,
        signature_algorithm VARCHAR(32) NULL,
        signature_key_version INT NULL,
        signature_status VARCHAR(32) NOT NULL
            CONSTRAINT DF_client_position_labels_sig_status DEFAULT ('UNSIGNED'),
        created_by VARCHAR(128) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        invalidated_at DATETIME2 NULL,
        invalidation_reason NVARCHAR(512) NULL,
        idempotency_key NVARCHAR(128) NULL,
        idempotency_request_hash VARCHAR(64) NULL,
        CONSTRAINT PK_client_position_labels PRIMARY KEY (id),
        CONSTRAINT FK_client_position_labels_client
            FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT CK_client_position_labels_status CHECK (status IN ('ACTIVE', 'INVALIDATED')),
        CONSTRAINT CK_client_position_labels_signature_status CHECK (
            signature_status IN ('NOT_IMPLEMENTED', 'UNSIGNED', 'SIGNED')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_public_identifier'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_labels_public_identifier
        ON dbo.client_position_labels(public_identifier);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_client_position_labels_client_status'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE NONCLUSTERED INDEX IX_client_position_labels_client_status
        ON dbo.client_position_labels(client_id, status, created_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_client_idempotency'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_labels_client_idempotency
        ON dbo.client_position_labels(client_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL;
GO

-- ---------------------------------------------------------------------------
-- client_position_label_artifacts
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.client_position_label_artifacts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_position_label_artifacts (
        id VARCHAR(36) NOT NULL,
        label_id VARCHAR(36) NOT NULL,
        format VARCHAR(8) NOT NULL,
        preset VARCHAR(32) NOT NULL,
        template_version INT NOT NULL,
        marker_version INT NOT NULL,
        content_type VARCHAR(64) NOT NULL,
        file_size_bytes BIGINT NOT NULL,
        artifact_hash VARCHAR(64) NOT NULL,
        storage_key NVARCHAR(512) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_client_position_label_artifacts PRIMARY KEY (id),
        CONSTRAINT CK_client_position_label_artifacts_format CHECK (format IN ('PDF', 'PNG')),
        CONSTRAINT FK_client_position_label_artifacts_label
            FOREIGN KEY (label_id) REFERENCES dbo.client_position_labels(id)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_label_artifacts_identity'
      AND object_id = OBJECT_ID(N'dbo.client_position_label_artifacts')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_label_artifacts_identity
        ON dbo.client_position_label_artifacts(label_id, format, preset, template_version, marker_version);
GO

-- ---------------------------------------------------------------------------
-- Data migrate: aisle_location_labels → client_position_labels
-- ---------------------------------------------------------------------------
IF OBJECT_ID(N'dbo.aisle_location_labels', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.aisle_locations', N'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.client_position_labels (
        id, client_id, public_identifier, name, normalized_name, description,
        status, payload_version, canonical_payload, payload_hash,
        signature, signature_algorithm, signature_key_version, signature_status,
        created_by, created_at, updated_at, invalidated_at, invalidation_reason,
        idempotency_key, idempotency_request_hash
    )
    SELECT
        l.id,
        l.client_id,
        l.public_identifier,
        COALESCE(NULLIF(LTRIM(RTRIM(loc.display_name)), N''), loc.code),
        UPPER(COALESCE(NULLIF(LTRIM(RTRIM(loc.normalized_code)), N''), loc.code)),
        loc.description,
        CASE WHEN l.status = N'INVALIDATED' THEN N'INVALIDATED' ELSE N'ACTIVE' END,
        l.payload_version,
        CASE
            WHEN ISJSON(CONVERT(NVARCHAR(MAX), l.payload_json)) = 1
                THEN CONVERT(NVARCHAR(MAX), l.payload_json)
            ELSE N'{"type":"DINAMIC_POSITION","version":1,"label_id":"' + l.public_identifier + N'"}'
        END,
        l.payload_hash,
        CASE
            WHEN ISJSON(CONVERT(NVARCHAR(MAX), l.payload_json)) = 1
                THEN JSON_VALUE(CONVERT(NVARCHAR(MAX), l.payload_json), '$.signature')
            ELSE NULL
        END,
        CASE WHEN l.signature_status = N'SIGNED' THEN N'HMAC-SHA256' ELSE NULL END,
        CASE
            WHEN ISJSON(CONVERT(NVARCHAR(MAX), l.payload_json)) = 1
                THEN TRY_CONVERT(INT, JSON_VALUE(CONVERT(NVARCHAR(MAX), l.payload_json), '$.key_version'))
            ELSE NULL
        END,
        CASE
            WHEN l.signature_status IN (N'SIGNED', N'UNSIGNED', N'NOT_IMPLEMENTED')
                THEN l.signature_status
            ELSE N'UNSIGNED'
        END,
        l.generated_by,
        l.generated_at,
        COALESCE(l.generated_at, SYSUTCDATETIME()),
        l.invalidated_at,
        l.invalidation_reason,
        l.idempotency_key,
        l.idempotency_request_hash
    FROM dbo.aisle_location_labels l
    INNER JOIN dbo.aisle_locations loc ON loc.id = l.location_id
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.client_position_labels c WHERE c.id = l.id
    )
    AND NOT EXISTS (
        SELECT 1 FROM dbo.client_position_labels c2
        WHERE c2.public_identifier = l.public_identifier
    );
END
GO

IF OBJECT_ID(N'dbo.aisle_location_label_artifacts', N'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.client_position_label_artifacts (
        id, label_id, format, preset, template_version, marker_version,
        content_type, file_size_bytes, artifact_hash, storage_key, created_at
    )
    SELECT
        a.id, a.label_id, a.format, a.preset, a.template_version, a.marker_version,
        a.content_type, a.file_size_bytes, a.artifact_hash,
        COALESCE(a.storage_key, N'migrated-empty'), a.created_at
    FROM dbo.aisle_location_label_artifacts a
    INNER JOIN dbo.client_position_labels c ON c.id = a.label_id
    WHERE a.storage_key IS NOT NULL
      AND LTRIM(RTRIM(a.storage_key)) <> N''
      AND NOT EXISTS (
          SELECT 1 FROM dbo.client_position_label_artifacts x WHERE x.id = a.id
      );
END
GO
