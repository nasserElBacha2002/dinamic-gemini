/*
  DESTRUCTIVE ROLLBACK: disable both POSITION_AUTO_MATERIALIZATION_ENABLED and
  POSITION_MATERIALIZATION_RECOVERY_ENABLED, stop schedulers, and drain work.
  Receipt rows and all recovery attempt/lease history are permanently lost.

  Fail-closed preflight: there is deliberately no override. Before rollback,
  verify that the query below returns zero rows after the scheduler is stopped:
    SELECT id, association_status, lease_owner, lease_expires_at
    FROM dbo.position_materialization_requests
    WHERE association_status IN ('PENDING', 'REQUIRES_REVIEW', 'EXHAUSTED')
       OR lease_owner IS NOT NULL OR lease_expires_at IS NOT NULL;
*/

IF EXISTS (
    SELECT 1
    FROM dbo.position_materialization_requests
    WHERE association_status IN ('PENDING', 'REQUIRES_REVIEW', 'EXHAUSTED')
       OR lease_owner IS NOT NULL
       OR lease_expires_at IS NOT NULL
)
    THROW 51016,
        '0106 rollback requires recovery flags off and all pending/review/exhausted/leased work drained',
        1;
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'IX_pmr_association_due'
)
    DROP INDEX IX_pmr_association_due ON dbo.position_materialization_requests;
GO

IF OBJECT_ID(N'dbo.position_materialization_association_receipts', N'U') IS NOT NULL
    DROP TABLE dbo.position_materialization_association_receipts;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_association_state'
)
    ALTER TABLE dbo.position_materialization_requests DROP CONSTRAINT CK_pmr_association_state;
GO
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_lease_pair'
)
    ALTER TABLE dbo.position_materialization_requests DROP CONSTRAINT CK_pmr_lease_pair;
GO
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'CK_pmr_attempt_count'
)
    ALTER TABLE dbo.position_materialization_requests DROP CONSTRAINT CK_pmr_attempt_count;
GO

ALTER TABLE dbo.position_materialization_requests
    ADD CONSTRAINT CK_pmr_association_state CHECK (
        (association_status = 'PENDING'
            AND associated_at IS NULL AND association_error_code IS NULL)
        OR (association_status = 'ASSOCIATED'
            AND associated_at IS NOT NULL AND association_error_code IS NULL)
        OR (association_status = 'REQUIRES_REVIEW'
            AND associated_at IS NULL AND association_error_code IS NOT NULL)
    );
GO

IF COL_LENGTH(N'dbo.position_materialization_requests', N'lease_expires_at') IS NOT NULL
    ALTER TABLE dbo.position_materialization_requests DROP COLUMN lease_expires_at;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'lease_owner') IS NOT NULL
    ALTER TABLE dbo.position_materialization_requests DROP COLUMN lease_owner;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'next_retry_at') IS NOT NULL
    ALTER TABLE dbo.position_materialization_requests DROP COLUMN next_retry_at;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'last_attempt_at') IS NOT NULL
    ALTER TABLE dbo.position_materialization_requests DROP COLUMN last_attempt_at;
GO
IF EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_requests')
      AND name = N'DF_pmr_attempt_count'
)
    ALTER TABLE dbo.position_materialization_requests DROP CONSTRAINT DF_pmr_attempt_count;
GO
IF COL_LENGTH(N'dbo.position_materialization_requests', N'attempt_count') IS NOT NULL
    ALTER TABLE dbo.position_materialization_requests DROP COLUMN attempt_count;
GO
