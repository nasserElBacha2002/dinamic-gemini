-- Soft-deactivate support for aisles (additive).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'is_active')
    ALTER TABLE aisles ADD is_active BIT NOT NULL CONSTRAINT DF_aisles_is_active DEFAULT 1;
GO
