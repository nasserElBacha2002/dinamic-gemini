/*
  0092_client_position_label_active_marker_unique.down.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_active_marker'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    DROP INDEX UQ_client_position_labels_active_marker ON dbo.client_position_labels;
GO
