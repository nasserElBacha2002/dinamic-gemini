-- Phase A2 — client suppliers foundation (additive).

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'client_suppliers')
BEGIN
    CREATE TABLE client_suppliers (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        client_id VARCHAR(36) NOT NULL,
        name NVARCHAR(255) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_client_suppliers_client FOREIGN KEY (client_id) REFERENCES clients(id),
        CONSTRAINT UQ_client_suppliers_client_name UNIQUE (client_id, name)
    );
    CREATE INDEX IX_client_suppliers_client_id ON client_suppliers(client_id);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID('client_suppliers') AND name = 'DF_client_suppliers_status'
)
    ALTER TABLE client_suppliers ADD CONSTRAINT DF_client_suppliers_status DEFAULT ('active') FOR status;
GO

