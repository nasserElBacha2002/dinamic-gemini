-- Phase 6: authoritative aisle finalization (local CODE_SCAN close without remote reprocess).
-- Additive / idempotent. Disable via SERVER_AUTHORITATIVE_AISLE_FINALIZATION=false.
-- Formal rollback (dev/test only):
--   DROP TABLE IF EXISTS authoritative_aisle_finalization_items;
--   DROP TABLE IF EXISTS authoritative_aisle_finalization_locks;
--   DROP TABLE IF EXISTS authoritative_aisle_excluded_assets;
--   DROP TABLE IF EXISTS authoritative_aisle_finalizations;

IF OBJECT_ID('authoritative_aisle_finalizations', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_finalizations (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        capture_session_id VARCHAR(36) NULL,
        finalization_version INT NOT NULL,
        status VARCHAR(40) NOT NULL,
        total_assets INT NOT NULL,
        applied_assets INT NOT NULL,
        excluded_assets INT NOT NULL,
        position_count INT NOT NULL,
        expected_asset_count INT NULL,
        content_hash VARCHAR(80) NOT NULL,
        confirmed_by VARCHAR(36) NOT NULL,
        confirmed_at DATETIME2 NOT NULL,
        completed_at DATETIME2 NULL,
        is_current BIT NOT NULL CONSTRAINT DF_aaf_is_current DEFAULT (1),
        row_version INT NOT NULL CONSTRAINT DF_aaf_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_authoritative_aisle_finalizations PRIMARY KEY (id),
        CONSTRAINT UQ_aaf_aisle_version UNIQUE (aisle_id, finalization_version),
        CONSTRAINT FK_aaf_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aaf_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_aaf_finalization_version CHECK (finalization_version >= 1),
        CONSTRAINT CK_aaf_counts CHECK (
            total_assets >= 0 AND applied_assets >= 0 AND excluded_assets >= 0
            AND position_count >= 0
            AND applied_assets + excluded_assets <= total_assets
        ),
        CONSTRAINT CK_aaf_status CHECK (
            status IN (
                'FINALIZING',
                'COMPLETED_BY_LOCAL_AUTHORITY',
                'FINALIZATION_FAILED',
                'CANCELED'
            )
        )
    );
END
GO

IF OBJECT_ID('authoritative_aisle_finalizations', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_aaf_aisle_current'
          AND object_id = OBJECT_ID('authoritative_aisle_finalizations')
   )
    CREATE UNIQUE INDEX IX_aaf_aisle_current
        ON authoritative_aisle_finalizations (aisle_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('authoritative_aisle_finalization_items', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_finalization_items (
        id VARCHAR(36) NOT NULL,
        finalization_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        authoritative_result_id VARCHAR(36) NULL,
        position_id VARCHAR(36) NULL,
        item_status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aafi PRIMARY KEY (id),
        CONSTRAINT UQ_aafi_finalization_asset UNIQUE (finalization_id, asset_id),
        CONSTRAINT FK_aafi_finalization FOREIGN KEY (finalization_id)
            REFERENCES authoritative_aisle_finalizations(id),
        CONSTRAINT CK_aafi_item_status CHECK (
            item_status IN ('CONFIRMED_AND_APPLIED', 'EXCLUDED')
        )
    );
END
GO

IF OBJECT_ID('authoritative_aisle_finalization_items', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_aafi_finalization'
          AND object_id = OBJECT_ID('authoritative_aisle_finalization_items')
   )
    CREATE INDEX IX_aafi_finalization
        ON authoritative_aisle_finalization_items (finalization_id);
GO

IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_excluded_assets (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        reason VARCHAR(40) NOT NULL,
        excluded_by VARCHAR(36) NOT NULL,
        excluded_at DATETIME2 NOT NULL,
        is_current BIT NOT NULL CONSTRAINT DF_aaea_is_current DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aaea PRIMARY KEY (id),
        CONSTRAINT FK_aaea_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aaea_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_aaea_reason CHECK (
            reason IN (
                'DUPLICATE_PHOTO',
                'INVALID_PHOTO',
                'NOT_INVENTORY_LABEL',
                'USER_EXCLUDED',
                'CAPTURE_ERROR'
            )
        )
    );
END
GO

IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_aaea_aisle_asset_current'
          AND object_id = OBJECT_ID('authoritative_aisle_excluded_assets')
   )
    CREATE UNIQUE INDEX UQ_aaea_aisle_asset_current
        ON authoritative_aisle_excluded_assets (aisle_id, asset_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_aaea_aisle_current'
          AND object_id = OBJECT_ID('authoritative_aisle_excluded_assets')
   )
    CREATE INDEX IX_aaea_aisle_current
        ON authoritative_aisle_excluded_assets (inventory_id, aisle_id, is_current);
GO

IF OBJECT_ID('authoritative_aisle_finalization_locks', 'U') IS NULL
BEGIN
    CREATE TABLE authoritative_aisle_finalization_locks (
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        owner_token VARCHAR(64) NOT NULL,
        lease_expires_at DATETIME2 NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aafl PRIMARY KEY (aisle_id),
        CONSTRAINT FK_aafl_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_aafl_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
END
GO
