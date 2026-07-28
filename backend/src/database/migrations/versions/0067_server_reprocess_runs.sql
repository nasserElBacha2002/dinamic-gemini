-- Phase 7: optional server reprocess (proposals; no automatic overwrite of current results).
-- Additive / idempotent. Disable via SERVER_SERVER_REPROCESS=false.
-- Formal rollback (dev/test only):
--   DROP TABLE IF EXISTS server_reprocess_adoption_items;
--   DROP TABLE IF EXISTS server_reprocess_adoptions;
--   DROP TABLE IF EXISTS server_reprocess_proposals;
--   DROP TABLE IF EXISTS server_reprocess_run_assets;
--   DROP TABLE IF EXISTS server_reprocess_runs;
--   DROP TABLE IF EXISTS server_reprocess_locks;

IF OBJECT_ID('server_reprocess_runs', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_runs (
        id VARCHAR(36) NOT NULL,
        request_id VARCHAR(64) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        source_session_id VARCHAR(36) NULL,
        company_id VARCHAR(36) NULL,
        run_type VARCHAR(40) NOT NULL,
        strategy VARCHAR(40) NULL,
        scope_type VARCHAR(40) NOT NULL,
        scope_json NVARCHAR(MAX) NOT NULL,
        snapshot_json NVARCHAR(MAX) NOT NULL,
        processing_mode VARCHAR(40) NOT NULL,
        reason VARCHAR(80) NOT NULL,
        status VARCHAR(32) NOT NULL,
        review_status VARCHAR(40) NOT NULL,
        requested_by VARCHAR(36) NOT NULL,
        requested_at DATETIME2 NOT NULL,
        started_at DATETIME2 NULL,
        completed_at DATETIME2 NULL,
        canceled_at DATETIME2 NULL,
        failed_at DATETIME2 NULL,
        failure_code VARCHAR(80) NULL,
        failure_message NVARCHAR(500) NULL,
        pipeline_version VARCHAR(64) NULL,
        model_version VARCHAR(64) NULL,
        prompt_version VARCHAR(64) NULL,
        supplier_profile_id VARCHAR(36) NULL,
        linked_job_id VARCHAR(36) NULL,
        has_prior_authority BIT NOT NULL CONSTRAINT DF_srr_has_prior DEFAULT (1),
        row_version INT NOT NULL CONSTRAINT DF_srr_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_runs PRIMARY KEY (id),
        CONSTRAINT UQ_srr_request_id UNIQUE (request_id),
        CONSTRAINT FK_srr_inventory FOREIGN KEY (inventory_id) REFERENCES inventories(id),
        CONSTRAINT FK_srr_aisle FOREIGN KEY (aisle_id) REFERENCES aisles(id),
        CONSTRAINT CK_srr_run_type CHECK (
            run_type IN (
                'INITIAL_SERVER_PROCESSING',
                'SERVER_REPROCESS',
                'LOCAL_AUTHORITY_APPLY'
            )
        ),
        CONSTRAINT CK_srr_scope_type CHECK (
            scope_type IN (
                'FULL_AISLE',
                'SELECTED_ASSETS',
                'FAILED_ONLY',
                'UNRECOGNIZED_ONLY',
                'PENDING_REVIEW_ONLY'
            )
        ),
        CONSTRAINT CK_srr_status CHECK (
            status IN (
                'REQUESTED',
                'QUEUED',
                'RUNNING',
                'COMPLETED',
                'FAILED',
                'CANCELED',
                'TIMED_OUT',
                'PARTIAL'
            )
        ),
        CONSTRAINT CK_srr_review_status CHECK (
            review_status IN (
                'NOT_REVIEWED',
                'REVIEW_IN_PROGRESS',
                'REVIEW_COMPLETED',
                'DISCARDED',
                'ADOPTED_PARTIALLY',
                'ADOPTED_COMPLETELY'
            )
        ),
        CONSTRAINT CK_srr_processing_mode CHECK (
            processing_mode IN (
                'CODE_SCAN',
                'INTERNAL_OCR',
                'GLOBAL_FALLBACK',
                'AUTO_PIPELINE'
            )
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_runs', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srr_aisle_requested'
          AND object_id = OBJECT_ID('server_reprocess_runs')
   )
    CREATE INDEX IX_srr_aisle_requested
        ON server_reprocess_runs (aisle_id, requested_at DESC);
GO

IF OBJECT_ID('server_reprocess_run_assets', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_run_assets (
        id VARCHAR(36) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        asset_hash VARCHAR(128) NULL,
        previous_result_id VARCHAR(36) NULL,
        previous_position_id VARCHAR(36) NULL,
        previous_internal_code NVARCHAR(128) NULL,
        previous_quantity DECIMAL(18, 4) NULL,
        previous_resolved BIT NOT NULL CONSTRAINT DF_srra_prev_resolved DEFAULT (0),
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_run_assets PRIMARY KEY (id),
        CONSTRAINT UQ_srra_run_asset UNIQUE (run_id, asset_id),
        CONSTRAINT FK_srra_run FOREIGN KEY (run_id) REFERENCES server_reprocess_runs(id)
    );
END
GO

IF OBJECT_ID('server_reprocess_run_assets', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srra_run'
          AND object_id = OBJECT_ID('server_reprocess_run_assets')
   )
    CREATE INDEX IX_srra_run ON server_reprocess_run_assets (run_id);
GO

IF OBJECT_ID('server_reprocess_proposals', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_proposals (
        id VARCHAR(36) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        remote_result_id VARCHAR(36) NULL,
        previous_result_id VARCHAR(36) NULL,
        previous_position_id VARCHAR(36) NULL,
        status VARCHAR(40) NOT NULL,
        difference_type VARCHAR(64) NOT NULL,
        internal_code NVARCHAR(128) NULL,
        quantity DECIMAL(18, 4) NULL,
        confidence FLOAT NULL,
        source VARCHAR(64) NULL,
        pipeline_version VARCHAR(64) NULL,
        remote_resolved BIT NOT NULL CONSTRAINT DF_srp_remote_resolved DEFAULT (0),
        review_status VARCHAR(40) NOT NULL CONSTRAINT DF_srp_review DEFAULT ('NOT_REVIEWED'),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_proposals PRIMARY KEY (id),
        CONSTRAINT UQ_srp_run_asset UNIQUE (run_id, asset_id),
        CONSTRAINT FK_srp_run FOREIGN KEY (run_id) REFERENCES server_reprocess_runs(id),
        CONSTRAINT CK_srp_status CHECK (
            status IN (
                'PROPOSED',
                'ADOPTED',
                'KEPT_CURRENT',
                'DEFERRED',
                'DISCARDED',
                'STALE',
                'NOT_COMPARABLE'
            )
        ),
        CONSTRAINT CK_srp_difference CHECK (
            difference_type IN (
                'SAME_RESULT',
                'CODE_CHANGED',
                'QUANTITY_CHANGED',
                'CODE_AND_QUANTITY_CHANGED',
                'PREVIOUS_UNRESOLVED_REMOTE_RESOLVED',
                'PREVIOUS_RESOLVED_REMOTE_UNRESOLVED',
                'REMOTE_AMBIGUOUS',
                'NO_PREVIOUS_RESULT',
                'NOT_COMPARABLE',
                'NOT_COMPARABLE_GLOBAL_BATCH'
            )
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_proposals', 'U') IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = 'IX_srp_run_diff'
          AND object_id = OBJECT_ID('server_reprocess_proposals')
   )
    CREATE INDEX IX_srp_run_diff
        ON server_reprocess_proposals (run_id, difference_type);
GO

IF OBJECT_ID('server_reprocess_adoptions', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_adoptions (
        id VARCHAR(36) NOT NULL,
        adoption_id VARCHAR(64) NOT NULL,
        run_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        status VARCHAR(32) NOT NULL,
        adopted_by VARCHAR(36) NOT NULL,
        adopted_at DATETIME2 NOT NULL,
        item_count INT NOT NULL,
        adopted_count INT NOT NULL,
        kept_count INT NOT NULL,
        deferred_count INT NOT NULL,
        row_version INT NOT NULL CONSTRAINT DF_sra_row_version DEFAULT (1),
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_adoptions PRIMARY KEY (id),
        CONSTRAINT UQ_sra_adoption_id UNIQUE (adoption_id),
        CONSTRAINT FK_sra_run FOREIGN KEY (run_id) REFERENCES server_reprocess_runs(id),
        CONSTRAINT CK_sra_status CHECK (
            status IN ('COMPLETED', 'FAILED', 'ROLLED_BACK')
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_adoption_items', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_adoption_items (
        id VARCHAR(36) NOT NULL,
        adoption_row_id VARCHAR(36) NOT NULL,
        proposal_id VARCHAR(36) NOT NULL,
        asset_id VARCHAR(36) NOT NULL,
        action VARCHAR(32) NOT NULL,
        expected_previous_result_id VARCHAR(36) NULL,
        new_result_id VARCHAR(36) NULL,
        new_position_id VARCHAR(36) NULL,
        edit_internal_code NVARCHAR(128) NULL,
        edit_quantity DECIMAL(18, 4) NULL,
        created_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_adoption_items PRIMARY KEY (id),
        CONSTRAINT UQ_srai_adoption_proposal UNIQUE (adoption_row_id, proposal_id),
        CONSTRAINT FK_srai_adoption FOREIGN KEY (adoption_row_id)
            REFERENCES server_reprocess_adoptions(id),
        CONSTRAINT FK_srai_proposal FOREIGN KEY (proposal_id)
            REFERENCES server_reprocess_proposals(id),
        CONSTRAINT CK_srai_action CHECK (
            action IN ('ADOPT', 'KEEP_CURRENT', 'EDIT_AND_ADOPT', 'DEFER')
        )
    );
END
GO

IF OBJECT_ID('server_reprocess_locks', 'U') IS NULL
BEGIN
    CREATE TABLE server_reprocess_locks (
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        owner_token VARCHAR(64) NOT NULL,
        expires_at DATETIME2 NOT NULL,
        CONSTRAINT PK_server_reprocess_locks PRIMARY KEY (aisle_id)
    );
END
GO
