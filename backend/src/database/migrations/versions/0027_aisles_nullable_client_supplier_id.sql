-- Phase A4 — nullable aisle->client_supplier relation foundation (additive).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'client_supplier_id')
    ALTER TABLE aisles ADD client_supplier_id VARCHAR(36) NULL;
GO
IF NOT EXISTS (
    SELECT * FROM sys.foreign_keys WHERE name = 'FK_aisles_client_supplier'
)
BEGIN
    ALTER TABLE aisles
    ADD CONSTRAINT FK_aisles_client_supplier
    FOREIGN KEY (client_supplier_id) REFERENCES client_suppliers(id);
END;
GO
IF NOT EXISTS (
    SELECT * FROM sys.indexes WHERE name = 'IX_aisles_client_supplier_id' AND object_id = OBJECT_ID('aisles')
)
    CREATE INDEX IX_aisles_client_supplier_id ON aisles(client_supplier_id);
GO

