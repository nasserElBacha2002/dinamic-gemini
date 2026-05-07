-- Phase A1 — clients foundation (additive).

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'clients')
BEGIN
    CREATE TABLE clients (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        name NVARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL
    );
    CREATE INDEX IX_clients_created_at ON clients(created_at DESC);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('clients') AND name = 'DF_clients_status'
)
    ALTER TABLE clients ADD CONSTRAINT DF_clients_status DEFAULT ('active') FOR status;
GO
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_clients_name' AND object_id = OBJECT_ID('clients'))
    CREATE INDEX IX_clients_name ON clients(name);
GO

