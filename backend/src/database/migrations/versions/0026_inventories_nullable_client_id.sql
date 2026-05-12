-- Phase A3 — nullable inventory->client relation foundation (additive).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('inventories') AND name = 'client_id')
    ALTER TABLE inventories ADD client_id VARCHAR(36) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys WHERE name = 'FK_inventories_client'
)
BEGIN
    ALTER TABLE inventories
    ADD CONSTRAINT FK_inventories_client
    FOREIGN KEY (client_id) REFERENCES clients(id);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'IX_inventories_client_id' AND object_id = OBJECT_ID('inventories')
)
    CREATE INDEX IX_inventories_client_id ON inventories(client_id);
GO

