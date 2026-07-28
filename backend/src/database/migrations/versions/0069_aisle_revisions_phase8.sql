-- Phase 8: aisle revisions, position versions, finalization lineage.
-- Additive / idempotent. Disable via SERVER_AISLE_REVISIONS=false.
-- Formal rollback (dev/test only):
--   DROP TABLE IF EXISTS aisle_revision_items;
--   DROP TABLE IF EXISTS aisle_revision_locks;
--   DROP TABLE IF EXISTS aisle_revisions;
--   DROP TABLE IF EXISTS position_versions;
--   ALTER TABLE authoritative_aisle_finalizations DROP COLUMN supersedes_finalization_id;
--   ALTER TABLE authoritative_aisle_finalizations DROP COLUMN revision_id;
--   ALTER TABLE aisles DROP COLUMN revision_status;

IF COL_LENGTH('aisles', 'revision_status') IS NULL
BEGIN
    ALTER TABLE aisles ADD revision_status VARCHAR(32) NULL;
END
GO

IF COL_LENGTH('authoritative_aisle_finalizations', 'supersedes_finalization_id') IS NULL
BEGIN
    ALTER TABLE authoritative_aisle_finalizations
        ADD supersedes_finalization_id VARCHAR(36) NULL;
END
GO

IF COL_LENGTH('authoritative_aisle_finalizations', 'revision_id') IS NULL
BEGIN
    ALTER TABLE authoritative_aisle_finalizations
        ADD revision_id VARCHAR(36) NULL;
END
GO

IF OBJECT_ID('position_versions', 'U') IS NULL
BEGIN
    CREATE TABLE position_versions (
        id VARCHAR(36) NOT NULL,
        position_id VARCHAR(36) NOT NULL,
        version INT NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        internal_code VARCHAR(128) NOT NULL,
        quantity INT NULL,
        result_id VARCHAR(36) NULL,
        is_current BIT NOT NULL CONSTRAINT DF_pv_is_current DEFAULT (1),
        supersedes_position_version_id VARCHAR(36) NULL,
        revision_id VARCHAR(36) NULL,
        revision_item_id VARCHAR(36) NULL,
        created_by VARCHAR(36) NOT NULL,
        created_at DATETIME2 NOT NULL,
        content_hash VARCHAR(80) NOT NULL,
        CONSTRAINT PK_position_versions PRIMARY KEY (id),
        CONSTRAINT UQ_pv_position_version UNIQUE (position_id, version),
        CONSTRAINT FK_pv_position FOREIGN KEY (position_id) REFERENCES positions(id),
        CONSTRAINT FK_pv_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_pv_version CHECK (version >= 1)
    );
END
GO

IF OBJECT_ID('position_versions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pv_position_current'
          AND object_id = OBJECT_ID('position_versions')
   )
    CREATE UNIQUE INDEX IX_pv_position_current
        ON position_versions (position_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('position_versions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_pv_aisle_asset'
          AND object_id = OBJECT_ID('position_versions')
   )
    CREATE INDEX IX_pv_aisle_asset
        ON position_versions (aisle_id, asset_id);
GO

IF OBJECT_ID('aisle_revisions', 'U') IS NULL
BEGIN
    CREATE TABLE aisle_revisions (
        id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        base_finalization_id VARCHAR(36) NOT NULL,
        new_finalization_id VARCHAR(36) NULL,
        revision_type VARCHAR(40) NOT NULL,
        status VARCHAR(32) NOT NULL,
        reason NVARCHAR(500) NOT NULL,
        requested_by VARCHAR(36) NOT NULL,
        requested_at DATETIME2 NOT NULL,
        started_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        canceled_at DATETIME2 NULL,
        failed_at DATETIME2 NULL,
        failure_code VARCHAR(64) NULL,
        failure_message NVARCHAR(500) NULL,
        apply_id VARCHAR(36) NULL,
        snapshot_json NVARCHAR(MAX) NOT NULL,
        content_hash VARCHAR(80) NOT NULL,
        row_version INT NOT NULL CONSTRAINT DF_ar_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aisle_revisions PRIMARY KEY (id),
        CONSTRAINT FK_ar_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_ar_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_ar_revision_type CHECK (
            revision_type IN (
                'MANUAL_CORRECTION',
                'SERVER_PROPOSAL_ADOPTION',
                'ROLLBACK',
                'EXCLUSION_CHANGE',
                'REOPEN_AND_EDIT'
            )
        ),
        CONSTRAINT CK_ar_status CHECK (
            status IN (
                'DRAFT',
                'OPEN',
                'IN_REVIEW',
                'READY_TO_APPLY',
                'APPLYING',
                'COMPLETED',
                'CANCELED',
                'FAILED',
                'CONFLICTED'
            )
        )
    );
END
GO

IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ar_aisle_status'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE INDEX IX_ar_aisle_status
        ON aisle_revisions (aisle_id, status);
GO

IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ar_aisle_open'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE UNIQUE INDEX IX_ar_aisle_open
        ON aisle_revisions (aisle_id)
        WHERE status IN ('DRAFT', 'OPEN', 'IN_REVIEW', 'READY_TO_APPLY', 'APPLYING');
GO

IF OBJECT_ID('aisle_revision_items', 'U') IS NULL
BEGIN
    CREATE TABLE aisle_revision_items (
        id VARCHAR(36) NOT NULL,
        revision_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        base_result_id VARCHAR(36) NULL,
        base_position_id VARCHAR(36) NULL,
        proposed_internal_code VARCHAR(128) NULL,
        proposed_quantity INT NULL,
        proposed_exclusion_state VARCHAR(16) NULL,
        proposal_source VARCHAR(40) NOT NULL,
        proposal_reference_id VARCHAR(36) NULL,
        change_reason NVARCHAR(500) NULL,
        item_status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_ari PRIMARY KEY (id),
        CONSTRAINT UQ_ari_revision_asset UNIQUE (revision_id, asset_id),
        CONSTRAINT FK_ari_revision FOREIGN KEY (revision_id) REFERENCES aisle_revisions(id),
        CONSTRAINT CK_ari_proposal_source CHECK (
            proposal_source IN (
                'MANUAL',
                'SERVER_REPROCESS_PROPOSAL',
                'ROLLBACK_SOURCE',
                'EXCLUSION_CHANGE',
                'UNCHANGED'
            )
        ),
        CONSTRAINT CK_ari_item_status CHECK (
            item_status IN (
                'UNCHANGED',
                'MODIFIED',
                'EXCLUDED',
                'RESTORED',
                'ADOPT_REMOTE',
                'ROLLED_BACK',
                'CONFLICTED'
            )
        ),
        CONSTRAINT CK_ari_exclusion_state CHECK (
            proposed_exclusion_state IS NULL
            OR proposed_exclusion_state IN ('EXCLUDE', 'RESTORE', 'KEEP')
        )
    );
END
GO

IF OBJECT_ID('aisle_revision_items', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ari_revision'
          AND object_id = OBJECT_ID('aisle_revision_items')
   )
    CREATE INDEX IX_ari_revision
        ON aisle_revision_items (revision_id);
GO

IF OBJECT_ID('aisle_revision_locks', 'U') IS NULL
BEGIN
    CREATE TABLE aisle_revision_locks (
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        owner_token VARCHAR(64) NOT NULL,
        lease_expires_at DATETIME2 NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_aisle_revision_locks PRIMARY KEY (aisle_id)
    );
END
GO
