/*
  DIN-508 Phase 4 — rollback publish block columns.
*/

IF OBJECT_ID(N'dbo.aisle_live_channel_credentials', N'U') IS NOT NULL
AND EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_live_channel_credentials')
      AND name = N'publish_blocked_at'
)
BEGIN
    ALTER TABLE dbo.aisle_live_channel_credentials
    DROP COLUMN publish_blocked_at,
                publish_blocked_by_principal_id;
END;
GO