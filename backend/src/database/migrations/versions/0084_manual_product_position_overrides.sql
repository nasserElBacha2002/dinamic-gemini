/*
  Phase 6: immutable manual product-position override revisions.
  Automatic assignments and reconciliations remain unchanged.
*/
IF OBJECT_ID(N'dbo.manual_product_position_overrides', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.manual_product_position_overrides (
        id VARCHAR(36) NOT NULL,
        client_id VARCHAR(36) NOT NULL,
        inventory_id VARCHAR(36) NOT NULL,
        aisle_id VARCHAR(36) NOT NULL,
        job_id VARCHAR(36) NOT NULL,
        result_id VARCHAR(36) NOT NULL,
        source_asset_id VARCHAR(36) NULL,
        automatic_assignment_id VARCHAR(36) NULL,
        automatic_reconciliation_id VARCHAR(36) NULL,
        previous_effective_position_label_id VARCHAR(36) NULL,
        new_position_label_id VARCHAR(36) NULL,
        new_position_name_snapshot NVARCHAR(200) NULL,
        override_action VARCHAR(32) NOT NULL,
        reason_code VARCHAR(64) NOT NULL,
        reason_text NVARCHAR(1000) NULL,
        created_by_user_id VARCHAR(128) NOT NULL,
        created_by_role VARCHAR(64) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        version INT NOT NULL,
        is_active BIT NOT NULL,
        superseded_override_id VARCHAR(36) NULL,
        created_at DATETIME2 NOT NULL,
        updated_at DATETIME2 NOT NULL,
        deactivated_at DATETIME2 NULL,
        CONSTRAINT PK_manual_product_position_overrides PRIMARY KEY (id),
        CONSTRAINT FK_mppo_client FOREIGN KEY (client_id) REFERENCES dbo.clients(id),
        CONSTRAINT FK_mppo_inventory FOREIGN KEY (inventory_id) REFERENCES dbo.inventories(id),
        CONSTRAINT FK_mppo_aisle FOREIGN KEY (aisle_id) REFERENCES dbo.aisles(id),
        CONSTRAINT FK_mppo_job FOREIGN KEY (job_id) REFERENCES dbo.inventory_jobs(id),
        CONSTRAINT FK_mppo_result FOREIGN KEY (result_id) REFERENCES dbo.product_records(id),
        CONSTRAINT FK_mppo_asset FOREIGN KEY (source_asset_id) REFERENCES dbo.source_assets(id),
        CONSTRAINT FK_mppo_auto_assignment FOREIGN KEY (automatic_assignment_id)
            REFERENCES dbo.product_position_assignments(id),
        CONSTRAINT FK_mppo_auto_reconciliation FOREIGN KEY (automatic_reconciliation_id)
            REFERENCES dbo.position_reconciliations(id),
        CONSTRAINT FK_mppo_previous_label FOREIGN KEY (previous_effective_position_label_id)
            REFERENCES dbo.client_position_labels(id),
        CONSTRAINT FK_mppo_new_label FOREIGN KEY (new_position_label_id)
            REFERENCES dbo.client_position_labels(id),
        CONSTRAINT FK_mppo_superseded FOREIGN KEY (superseded_override_id)
            REFERENCES dbo.manual_product_position_overrides(id),
        CONSTRAINT CK_mppo_version CHECK (version > 0),
        CONSTRAINT CK_mppo_action CHECK (
            override_action IN (
                'ASSIGN_POSITION', 'CHANGE_POSITION', 'REMOVE_POSITION', 'RESTORE_AUTOMATIC'
            )
        ),
        CONSTRAINT CK_mppo_reason CHECK (
            reason_code IN (
                'WRONG_POSITION_DETECTED', 'PRODUCT_MOVED', 'SEQUENCE_ERROR',
                'POSITION_LABEL_NOT_VISIBLE', 'POSITION_LABEL_INVALID', 'AMBIGUOUS_IMAGE',
                'MISSING_POSITION_LABEL', 'OPERATOR_VERIFICATION', 'DATA_CORRECTION', 'OTHER'
            )
        ),
        CONSTRAINT CK_mppo_action_position CHECK (
            (override_action IN ('ASSIGN_POSITION', 'CHANGE_POSITION')
                AND new_position_label_id IS NOT NULL)
            OR (override_action IN ('REMOVE_POSITION', 'RESTORE_AUTOMATIC')
                AND new_position_label_id IS NULL)
        ),
        CONSTRAINT CK_mppo_restore_inactive CHECK (
            override_action <> 'RESTORE_AUTOMATIC' OR is_active = 0
        ),
        CONSTRAINT CK_mppo_other_reason_text CHECK (
            reason_code <> 'OTHER' OR LEN(LTRIM(RTRIM(ISNULL(reason_text, '')))) > 0
        )
    );
END
GO

CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_position_override_active
    ON dbo.manual_product_position_overrides(job_id, result_id) WHERE is_active = 1;
GO
CREATE UNIQUE NONCLUSTERED INDEX UQ_manual_position_override_idempotency
    ON dbo.manual_product_position_overrides(client_id, idempotency_key);
GO
CREATE NONCLUSTERED INDEX IX_mppo_job_result
    ON dbo.manual_product_position_overrides(job_id, result_id, version DESC);
GO
CREATE NONCLUSTERED INDEX IX_mppo_new_label
    ON dbo.manual_product_position_overrides(new_position_label_id)
    WHERE new_position_label_id IS NOT NULL;
GO
CREATE NONCLUSTERED INDEX IX_mppo_created_by
    ON dbo.manual_product_position_overrides(created_by_user_id);
GO
CREATE NONCLUSTERED INDEX IX_mppo_created_at
    ON dbo.manual_product_position_overrides(created_at);
GO
CREATE NONCLUSTERED INDEX IX_mppo_active_reason
    ON dbo.manual_product_position_overrides(is_active, reason_code);
GO
