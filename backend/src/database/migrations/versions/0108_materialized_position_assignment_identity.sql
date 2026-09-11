/*
  Version 0108 — durable detection-to-location identity for reconciliation.
  Additive, nullable, and safe to re-run against existing rows.
*/

IF COL_LENGTH(N'dbo.product_position_assignments', N'aisle_location_id') IS NULL
    ALTER TABLE dbo.product_position_assignments ADD aisle_location_id VARCHAR(36) NULL;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(N'dbo.product_position_assignments')
      AND name = N'FK_ppa_aisle_location'
)
    ALTER TABLE dbo.product_position_assignments WITH CHECK
        ADD CONSTRAINT FK_ppa_aisle_location FOREIGN KEY (aisle_location_id)
            REFERENCES dbo.aisle_locations(id);
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.product_position_assignments')
      AND name = N'CK_ppa_automatic_evidence'
)
    ALTER TABLE dbo.product_position_assignments
        DROP CONSTRAINT CK_ppa_automatic_evidence;
GO
ALTER TABLE dbo.product_position_assignments WITH CHECK
    ADD CONSTRAINT CK_ppa_automatic_evidence CHECK (
        assignment_status <> 'ASSIGNED_AUTOMATIC'
        OR (
            source_detection_id IS NOT NULL
            AND (position_label_id IS NOT NULL OR aisle_location_id IS NOT NULL)
        )
    );
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.product_position_assignments')
      AND name = N'CK_ppa_unassigned_position_null'
)
    ALTER TABLE dbo.product_position_assignments
        DROP CONSTRAINT CK_ppa_unassigned_position_null;
GO
ALTER TABLE dbo.product_position_assignments WITH CHECK
    ADD CONSTRAINT CK_ppa_unassigned_position_null CHECK (
        assignment_status = 'ASSIGNED_AUTOMATIC'
        OR (position_label_id IS NULL AND aisle_location_id IS NULL)
    );
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_position_assignments')
      AND name = N'IX_ppa_aisle_location'
)
    CREATE NONCLUSTERED INDEX IX_ppa_aisle_location
        ON dbo.product_position_assignments(aisle_location_id)
        WHERE aisle_location_id IS NOT NULL;
GO

IF COL_LENGTH(
    N'dbo.position_materialization_association_receipts', N'source_detection_id'
) IS NULL
    ALTER TABLE dbo.position_materialization_association_receipts
        ADD source_detection_id VARCHAR(36) NULL;
GO

IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(
        N'dbo.position_materialization_association_receipts'
    )
      AND name = N'FK_pmar_source_detection'
      AND delete_referential_action <> 2
)
    ALTER TABLE dbo.position_materialization_association_receipts
        DROP CONSTRAINT FK_pmar_source_detection;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(
        N'dbo.position_materialization_association_receipts'
    )
      AND name = N'FK_pmar_source_detection'
      AND delete_referential_action = 2
)
    ALTER TABLE dbo.position_materialization_association_receipts WITH CHECK
        ADD CONSTRAINT FK_pmar_source_detection FOREIGN KEY (source_detection_id)
            REFERENCES dbo.image_position_label_detections(id) ON DELETE SET NULL;
GO

IF EXISTS (
    SELECT source_detection_id
    FROM dbo.position_materialization_association_receipts
    WHERE source_detection_id IS NOT NULL
    GROUP BY source_detection_id
    HAVING COUNT_BIG(*) > 1
)
    THROW 51018, 'Duplicate materialization receipts exist for a source detection', 1;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(
        N'dbo.position_materialization_association_receipts'
    )
      AND name = N'UQ_pmar_source_detection'
)
    CREATE UNIQUE NONCLUSTERED INDEX UQ_pmar_source_detection
        ON dbo.position_materialization_association_receipts(source_detection_id)
        WHERE source_detection_id IS NOT NULL;
GO
