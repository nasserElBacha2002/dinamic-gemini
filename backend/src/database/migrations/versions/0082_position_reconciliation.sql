/*
  0082_position_reconciliation.sql

  Phase 4 — durable sequential product-to-position reconciliation.
  Rollback: 0082_position_reconciliation.down.sql
*/

IF OBJECT_ID(N'dbo.position_reconciliations', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.position_reconciliations (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        ordered_capture_session_id VARCHAR(36) NULL,
        reconciliation_name VARCHAR(100) NOT NULL,
        reconciliation_version VARCHAR(32) NOT NULL,
        input_fingerprint VARCHAR(64) NOT NULL,
        status VARCHAR(16) NOT NULL,
        started_at DATETIME2 NOT NULL,
        completed_at DATETIME2 NULL,
        failure_code VARCHAR(64) NULL,
        attempt_count INT NOT NULL,
        assigned_count INT NOT NULL,
        unassigned_count INT NOT NULL,
        sequence_gap_count INT NOT NULL,
        metadata_json NVARCHAR(MAX) NULL,
        is_active BIT NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        superseded_at DATETIME2 NULL,
        CONSTRAINT PK_position_reconciliations PRIMARY KEY (id),
        CONSTRAINT FK_position_reconciliations_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_position_reconciliations_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_position_reconciliations_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT CK_position_reconciliations_status CHECK (
            status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'STALE')
        )
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UQ_position_reconciliations_active_job'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_position_reconciliations_active_job
        ON dbo.position_reconciliations(job_id) WHERE is_active = 1;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_position_reconciliations_job'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_position_reconciliations_job
        ON dbo.position_reconciliations(job_id, created_at DESC);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_position_reconciliations_status'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_position_reconciliations_status
        ON dbo.position_reconciliations(status, updated_at);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_position_reconciliations_version'
      AND object_id = OBJECT_ID(N'dbo.position_reconciliations')
)
    CREATE NONCLUSTERED INDEX IX_position_reconciliations_version
        ON dbo.position_reconciliations(reconciliation_version, job_id);
GO

IF OBJECT_ID(N'dbo.product_position_assignments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_position_assignments (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        result_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NOT NULL,
        ordered_capture_session_id VARCHAR(36) NULL,
        sequence_number INT NULL,
        position_label_id VARCHAR(36) NULL,
        position_name_snapshot NVARCHAR(200) NULL,
        source_detection_id VARCHAR(36) NULL,
        assignment_status VARCHAR(64) NOT NULL,
        assignment_reason VARCHAR(128) NOT NULL,
        assignment_source VARCHAR(32) NULL,
        reconciliation_id VARCHAR(36) NOT NULL,
        reconciliation_version VARCHAR(32) NOT NULL,
        is_active BIT NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        superseded_at DATETIME2 NULL,
        CONSTRAINT PK_product_position_assignments PRIMARY KEY (id),
        CONSTRAINT FK_ppa_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_ppa_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_ppa_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_ppa_result FOREIGN KEY (result_id) REFERENCES dbo.product_records(id),
        CONSTRAINT FK_ppa_asset FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id),
        CONSTRAINT FK_ppa_label FOREIGN KEY (position_label_id) REFERENCES dbo.client_position_labels(id),
        CONSTRAINT FK_ppa_detection FOREIGN KEY (source_detection_id) REFERENCES dbo.image_position_label_detections(id),
        CONSTRAINT FK_ppa_reconciliation FOREIGN KEY (reconciliation_id) REFERENCES dbo.position_reconciliations(id)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UQ_ppa_active_job_result'
      AND object_id = OBJECT_ID(N'dbo.product_position_assignments')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_ppa_active_job_result
        ON dbo.product_position_assignments(job_id, result_id) WHERE is_active = 1;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_job' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_job ON dbo.product_position_assignments(job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_result' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_result ON dbo.product_position_assignments(result_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_position_label' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_position_label ON dbo.product_position_assignments(position_label_id) WHERE position_label_id IS NOT NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_assignment_status' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_assignment_status ON dbo.product_position_assignments(assignment_status, job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_reconciliation_version' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_reconciliation_version ON dbo.product_position_assignments(reconciliation_version, job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_is_active' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_is_active ON dbo.product_position_assignments(is_active, job_id);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_ppa_sequence_number' AND object_id = OBJECT_ID(N'dbo.product_position_assignments'))
    CREATE NONCLUSTERED INDEX IX_ppa_sequence_number ON dbo.product_position_assignments(job_id, sequence_number);
GO
