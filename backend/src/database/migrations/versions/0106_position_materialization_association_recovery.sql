/*
  Version 0106 — durable materialization-association recovery.
  Additive and safe to re-run. Existing ledger rows become PENDING, attempt 0,
  and immediately due without changing their pre-0106 materialization data.
*/

IF COL_LENGTH(N'dbo.position_materialization_requests', N'attempt_count') IS NULL
    ALTER TABLE dbo.position_materialization_requests
        ADD attempt_count INT NOT NULL
            CONSTRAINT DF_pmr_attempt_count DEFAULT (0) WITH VALUES;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'last_attempt_at') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD last_attempt_at DATETIME2 NULL;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'next_retry_at') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD next_retry_at DATETIME2 NULL;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'lease_owner') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD lease_owner VARCHAR(128) NULL;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'lease_expires_at') IS NULL
    ALTER TABLE dbo.position_materialization_requests ADD lease_expires_at DATETIME2 NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_association_state'
)
    ALTER TABLE dbo.position_materialization_requests
        DROP CONSTRAINT CK_pmr_association_state;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_attempt_count'
)
    ALTER TABLE dbo.position_materialization_requests
        ADD CONSTRAINT CK_pmr_attempt_count CHECK (attempt_count >= 0);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_lease_pair'
)
    ALTER TABLE dbo.position_materialization_requests
        ADD CONSTRAINT CK_pmr_lease_pair CHECK (
            (lease_owner IS NULL AND lease_expires_at IS NULL)
            OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_association_state'
)
    ALTER TABLE dbo.position_materialization_requests
        ADD CONSTRAINT CK_pmr_association_state CHECK (
            (association_status = 'PENDING' AND associated_at IS NULL
                AND (association_error_code IS NULL OR LEN(association_error_code) BETWEEN 1 AND 64))
            OR (association_status = 'ASSOCIATED' AND associated_at IS NOT NULL
                AND association_error_code IS NULL)
            OR (association_status IN ('REQUIRES_REVIEW', 'EXHAUSTED')
                AND associated_at IS NULL
                AND LEN(association_error_code) BETWEEN 1 AND 64)
        );
GO

IF OBJECT_ID(N'dbo.position_materialization_association_receipts', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.position_materialization_association_receipts (
        request_id VARCHAR(36) NOT NULL,
        target_type VARCHAR(24) NOT NULL,
        target_id VARCHAR(36) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_position_materialization_association_receipts PRIMARY KEY (request_id),
        CONSTRAINT FK_pmar_request FOREIGN KEY (request_id)
            REFERENCES dbo.position_materialization_requests(id),
        CONSTRAINT CK_pmar_target_type CHECK (target_type = 'IMAGE_RESULT'),
        CONSTRAINT CK_pmar_target_id CHECK (LEN(target_id) BETWEEN 1 AND 36)
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(
        N'dbo.position_materialization_association_receipts'
    )
      AND name = N'CK_pmar_target_type'
)
    ALTER TABLE dbo.position_materialization_association_receipts WITH CHECK
        ADD CONSTRAINT CK_pmar_target_type
            CHECK (target_type = 'IMAGE_RESULT');
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(
        N'dbo.position_materialization_association_receipts'
    )
      AND name = N'CK_pmar_target_id'
)
    ALTER TABLE dbo.position_materialization_association_receipts WITH CHECK
        ADD CONSTRAINT CK_pmar_target_id
            CHECK (LEN(target_id) BETWEEN 1 AND 36);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_association_receipts')
      AND name = N'IX_pmar_target'
)
    CREATE NONCLUSTERED INDEX IX_pmar_target
        ON dbo.position_materialization_association_receipts(target_type, target_id);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'IX_pmr_association_due'
)
    CREATE NONCLUSTERED INDEX IX_pmr_association_due
        ON dbo.position_materialization_requests(
            association_status, next_retry_at, lease_expires_at, attempt_count, created_at
        )
        INCLUDE (lease_owner);
GO
