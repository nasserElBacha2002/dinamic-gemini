-- Raspberry device credentials are client-scoped; only token hashes are stored.
IF OBJECT_ID(N'dbo.raspberry_devices', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.raspberry_devices (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        name NVARCHAR(200) NOT NULL,
        token_hash VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL,
        created_at DATETIME2 NOT NULL,
        last_used_at DATETIME2 NULL,
        CONSTRAINT PK_raspberry_devices PRIMARY KEY (id),
        CONSTRAINT FK_raspberry_devices_client
            FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT CK_raspberry_devices_status
            CHECK (status IN ('ACTIVE', 'REVOKED'))
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_raspberry_devices_token_hash'
      AND object_id = OBJECT_ID(N'dbo.raspberry_devices')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_raspberry_devices_token_hash
        ON dbo.raspberry_devices(token_hash);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_raspberry_devices_client_status'
      AND object_id = OBJECT_ID(N'dbo.raspberry_devices')
)
    CREATE NONCLUSTERED INDEX IX_raspberry_devices_client_status
        ON dbo.raspberry_devices(client_id, status);
GO