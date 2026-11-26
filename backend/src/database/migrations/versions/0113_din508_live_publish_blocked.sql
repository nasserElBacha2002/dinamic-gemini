/*
  DIN-508 Phase 4 — persist publish block after operator cuts transmission (additive).
*/

IF OBJECT_ID(N'dbo.aisle_live_channel_credentials', N'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.aisle_live_channel_credentials')
      AND name = N'publish_blocked_at'
)
BEGIN
    ALTER TABLE dbo.aisle_live_channel_credentials
    ADD publish_blocked_at DATETIME2 NULL,
        publish_blocked_by_principal_id NVARCHAR(64) NULL;
END;
GO