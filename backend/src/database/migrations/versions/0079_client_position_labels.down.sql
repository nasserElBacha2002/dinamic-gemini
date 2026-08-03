/*
  0079_client_position_labels.down.sql

  Manual rollback for 0079 (not executed by the UP-only migration runner).
  Drops new client-scoped tables. Does not restore aisle_location_* rows.
*/

IF OBJECT_ID(N'dbo.client_position_label_artifacts', N'U') IS NOT NULL
    DROP TABLE dbo.client_position_label_artifacts;
GO

IF OBJECT_ID(N'dbo.client_position_labels', N'U') IS NOT NULL
    DROP TABLE dbo.client_position_labels;
GO
