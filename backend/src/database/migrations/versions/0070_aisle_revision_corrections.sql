-- Phase 8 corrections: apply content hash, position CAS columns, uniqueness constraints.
-- Additive / idempotent. Requires 0069_aisle_revisions_phase8.
-- Formal rollback (dev/test only):
--   ALTER TABLE aisle_revisions DROP COLUMN apply_content_hash;
--   ALTER TABLE aisle_revision_items DROP COLUMN base_position_version_id;
--   ALTER TABLE aisle_revision_items DROP COLUMN base_position_row_version;
--   DROP INDEX IF EXISTS UQ_ar_apply_id ON aisle_revisions;
--   DROP INDEX IF EXISTS UQ_ar_apply_id_hash ON aisle_revisions;

IF COL_LENGTH('aisle_revisions', 'apply_content_hash') IS NULL
BEGIN
    ALTER TABLE aisle_revisions ADD apply_content_hash VARCHAR(80) NULL;
END
GO

IF COL_LENGTH('aisle_revision_items', 'base_position_version_id') IS NULL
BEGIN
    ALTER TABLE aisle_revision_items ADD base_position_version_id VARCHAR(36) NULL;
END
GO

IF COL_LENGTH('aisle_revision_items', 'base_position_row_version') IS NULL
BEGIN
    ALTER TABLE aisle_revision_items ADD base_position_row_version INT NULL;
END
GO

-- Unique apply_id when present (idempotent retries share the same id).
IF OBJECT_ID('aisle_revisions', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_ar_apply_id'
          AND object_id = OBJECT_ID('aisle_revisions')
   )
    CREATE UNIQUE INDEX UQ_ar_apply_id
        ON aisle_revisions (apply_id)
        WHERE apply_id IS NOT NULL;
GO

-- One current exclusion per asset (Phase 6 table; reinforce if missing).
IF OBJECT_ID('authoritative_aisle_excluded_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'UQ_aaea_current_asset'
          AND object_id = OBJECT_ID('authoritative_aisle_excluded_assets')
   )
    CREATE UNIQUE INDEX UQ_aaea_current_asset
        ON authoritative_aisle_excluded_assets (aisle_id, asset_id)
        WHERE is_current = 1;
GO

IF OBJECT_ID('aisle_revision_items', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_ari_revision_asset'
          AND object_id = OBJECT_ID('aisle_revision_items')
   )
    CREATE INDEX IX_ari_revision_asset
        ON aisle_revision_items (revision_id, asset_id);
GO
