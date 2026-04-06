-- Phase 2 — Operational job pointer per aisle (Result Context Resolver default reads).
-- Nullable FK: legacy aisles keep NULL; successful persist sets pointer to canonical run.
-- Keep aligned with backend/src/database/schema.sql (search operational_job_id on aisles).

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('aisles') AND name = 'operational_job_id')
BEGIN
    ALTER TABLE aisles ADD operational_job_id VARCHAR(36) NULL;
    ALTER TABLE aisles ADD CONSTRAINT FK_aisles_operational_job FOREIGN KEY (operational_job_id) REFERENCES inventory_jobs(id);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_aisles_operational_job_id' AND object_id = OBJECT_ID('aisles'))
    CREATE INDEX IX_aisles_operational_job_id ON aisles(operational_job_id);
GO
