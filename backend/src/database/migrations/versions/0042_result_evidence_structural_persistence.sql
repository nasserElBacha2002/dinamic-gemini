-- Phase 4.6 — Structural entity traceability evidence persistence
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'result_evidence')
CREATE TABLE result_evidence (
    id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    inventory_id VARCHAR(64) NOT NULL,
    aisle_id VARCHAR(64) NOT NULL,
    position_id VARCHAR(64) NULL,
    entity_uid VARCHAR(128) NULL,
    model_entity_id VARCHAR(128) NULL,
    raw_manifest_entry_id VARCHAR(64) NULL,
    manifest_entry_id VARCHAR(64) NULL,
    raw_source_image_id VARCHAR(256) NULL,
    resolved_manifest_entry_id VARCHAR(64) NULL,
    source_image_id VARCHAR(256) NULL,
    source_asset_id VARCHAR(64) NULL,
    traceability_status VARCHAR(32) NULL,
    traceability_warning NVARCHAR(1024) NULL,
    role VARCHAR(32) NULL,
    provider VARCHAR(64) NULL,
    model_name VARCHAR(128) NULL,
    schema_version VARCHAR(64) NULL,
    manifest_version INT NULL,
    has_valid_evidence BIT NOT NULL DEFAULT 0,
    evidence_kind VARCHAR(64) NOT NULL DEFAULT 'entity_traceability',
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_result_evidence PRIMARY KEY (id)
);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_id')
    CREATE INDEX IX_result_evidence_job_id ON result_evidence (job_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_entity_uid')
    CREATE INDEX IX_result_evidence_job_entity_uid ON result_evidence (job_id, entity_uid);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_model_entity_id')
    CREATE INDEX IX_result_evidence_job_model_entity_id ON result_evidence (job_id, model_entity_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_traceability_status')
    CREATE INDEX IX_result_evidence_job_traceability_status ON result_evidence (job_id, traceability_status);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_source_image_id')
    CREATE INDEX IX_result_evidence_job_source_image_id ON result_evidence (job_id, source_image_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_source_asset_id')
    CREATE INDEX IX_result_evidence_job_source_asset_id ON result_evidence (job_id, source_asset_id);
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_result_evidence_job_resolved_manifest_entry_id')
    CREATE INDEX IX_result_evidence_job_resolved_manifest_entry_id ON result_evidence (job_id, resolved_manifest_entry_id);
GO
