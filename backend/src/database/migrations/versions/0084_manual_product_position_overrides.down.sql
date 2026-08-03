/*
  WARNING: rollback deletes all manual position-override history.
  It does not modify or delete automatic assignments or reconciliations.
*/
IF OBJECT_ID(N'dbo.manual_product_position_overrides', N'U') IS NOT NULL
    DROP TABLE dbo.manual_product_position_overrides;
GO
