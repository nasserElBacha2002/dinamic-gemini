/*
  DIN-508 Phase 3 — live channel credentials + public view grants (additive).
*/

IF OBJECT_ID(N'dbo.aisle_live_channel_credentials', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.aisle_live_channel_credentials (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        canonical_aisle_code VARCHAR(64) NOT NULL,
        channel_slug VARCHAR(16) NOT NULL,
        mediamtx_path NVARCHAR(200) NOT NULL,
        publish_username NVARCHAR(80) NOT NULL,
        publish_password_hash NVARCHAR(255) NOT NULL,
        read_username NVARCHAR(80) NOT NULL,
        read_password_hash NVARCHAR(255) NOT NULL,
        created_by_principal_id NVARCHAR(64) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aisle_live_channel_credentials PRIMARY KEY (id),
        CONSTRAINT UQ_aisle_live_channel_inventory_slug UNIQUE (inventory_id, channel_slug),
        CONSTRAINT UQ_aisle_live_channel_path UNIQUE (mediamtx_path),
        CONSTRAINT UQ_aisle_live_channel_pub_user UNIQUE (publish_username),
        CONSTRAINT UQ_aisle_live_channel_read_user UNIQUE (read_username)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_aisle_live_channel_inventory'
      AND object_id = OBJECT_ID(N'dbo.aisle_live_channel_credentials')
)
BEGIN
    CREATE INDEX IX_aisle_live_channel_inventory
        ON dbo.aisle_live_channel_credentials (inventory_id);
END;
GO

IF OBJECT_ID(N'dbo.aisle_live_view_grants', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.aisle_live_view_grants (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        channel_slug VARCHAR(16) NOT NULL,
        mediamtx_path NVARCHAR(200) NOT NULL,
        token_hash NVARCHAR(128) NOT NULL,
        view_username NVARCHAR(80) NOT NULL,
        view_password_hash NVARCHAR(255) NOT NULL,
        created_by_principal_id NVARCHAR(64) NOT NULL,
        created_at DATETIME2 NOT NULL,
        expires_at DATETIME2 NOT NULL,
        revoked_at DATETIME2 NULL,
        CONSTRAINT PK_aisle_live_view_grants PRIMARY KEY (id),
        CONSTRAINT UQ_aisle_live_view_grants_token UNIQUE (token_hash),
        CONSTRAINT UQ_aisle_live_view_grants_view_user UNIQUE (view_username)
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_aisle_live_view_grants_channel'
      AND object_id = OBJECT_ID(N'dbo.aisle_live_view_grants')
)
BEGIN
    CREATE INDEX IX_aisle_live_view_grants_channel
        ON dbo.aisle_live_view_grants (inventory_id, channel_slug);
END;
GO