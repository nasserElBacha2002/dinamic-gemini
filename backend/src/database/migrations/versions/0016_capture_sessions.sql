-- Sprint 1 — Field capture sessions: sessions, staging items, confirm idempotency ledger.
-- Mirrors backend/src/database/schema.sql (capture_* block). Do not alter source_assets.

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_sessions')
BEGIN
    CREATE TABLE capture_sessions (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        opened_at DATETIME2 NULL,
        closed_at DATETIME2 NULL,
        CONSTRAINT FK_capture_sessions_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_capture_sessions_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id)
    );
    CREATE INDEX IX_capture_sessions_inventory_id ON capture_sessions(inventory_id);
    CREATE INDEX IX_capture_sessions_aisle_id ON capture_sessions(aisle_id);
    CREATE INDEX IX_capture_sessions_status_updated ON capture_sessions(status, updated_at);
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_session_items')
BEGIN
    CREATE TABLE capture_session_items (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        staging_storage_key NVARCHAR(1024) NOT NULL,
        content_hash NVARCHAR(128) NULL,
        effective_capture_time DATETIME2 NULL,
        time_source VARCHAR(32) NULL,
        time_confidence FLOAT NULL,
        import_status VARCHAR(32) NOT NULL,
        assignment_status VARCHAR(32) NOT NULL,
        linked_source_asset_id VARCHAR(36) NULL,
        last_error_code VARCHAR(64) NULL,
        last_error_detail NVARCHAR(512) NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT FK_capture_session_items_session FOREIGN KEY (session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
        CONSTRAINT FK_capture_session_items_source_asset FOREIGN KEY (linked_source_asset_id) REFERENCES source_assets(id)
    );
    CREATE INDEX IX_capture_session_items_session_id ON capture_session_items(session_id);
    CREATE INDEX IX_capture_session_items_linked_asset ON capture_session_items(linked_source_asset_id);
END;
GO

-- Filtered unique index: when ``content_hash`` is set, the same session cannot register two
-- items with the same hash (duplicate binary identity). Multiple rows with NULL hash are allowed.
IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_capture_session_items_session_content_hash'
      AND object_id = OBJECT_ID('capture_session_items')
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UQ_capture_session_items_session_content_hash
        ON capture_session_items(session_id, content_hash)
        WHERE content_hash IS NOT NULL;
END;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'capture_session_confirmations')
BEGIN
    CREATE TABLE capture_session_confirmations (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        session_id VARCHAR(36) NOT NULL,
        idempotency_key NVARCHAR(128) NOT NULL,
        outcome_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT FK_capture_session_confirmations_session FOREIGN KEY (session_id) REFERENCES capture_sessions(id) ON DELETE CASCADE,
        CONSTRAINT UQ_capture_session_confirmations_session_key UNIQUE (session_id, idempotency_key)
    );
    CREATE INDEX IX_capture_session_confirmations_session_id ON capture_session_confirmations(session_id);
END;
GO
