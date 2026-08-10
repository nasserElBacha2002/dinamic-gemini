/*
  0092_client_position_label_active_marker_unique.sql

  Enforce one ACTIVE marker identity per (client_id, pallet, side, level, marker_index).
  Reprint must invalidate the previous ACTIVE label before creating a replacement.

  Rollback: 0092_client_position_label_active_marker_unique.down.sql
*/

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_client_position_labels_active_marker'
      AND object_id = OBJECT_ID(N'dbo.client_position_labels')
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_client_position_labels_active_marker
        ON dbo.client_position_labels(client_id, pallet, side, level, marker_index)
        WHERE status = 'ACTIVE' AND pallet IS NOT NULL;
GO
