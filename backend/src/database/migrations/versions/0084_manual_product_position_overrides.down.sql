/*
  WARNING: rollback deletes all manual position-override history and drops the
  durable product_position_effective_versions table.
  It does not modify or delete automatic assignments or reconciliations.
*/
IF OBJECT_ID(N'dbo.manual_product_position_overrides', N'U') IS NOT NULL
    DROP TABLE dbo.manual_product_position_overrides;
GO
IF OBJECT_ID(N'dbo.product_position_effective_versions', N'U') IS NOT NULL
    DROP TABLE dbo.product_position_effective_versions;
GO
