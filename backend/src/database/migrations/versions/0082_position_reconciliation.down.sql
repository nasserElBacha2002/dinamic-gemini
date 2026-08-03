/*
  0082_position_reconciliation.down.sql
  Manual rollback for Phase 4 reconciliation persistence.
*/

IF OBJECT_ID(N'dbo.product_position_assignments', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.product_position_assignments;
END
GO

IF OBJECT_ID(N'dbo.position_reconciliations', N'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.position_reconciliations;
END
GO
