/*
  Guarded rollback: no durable materialized assignment or receipt identity may remain.
*/
IF COL_LENGTH(N'dbo.product_position_assignments', N'aisle_location_id') IS NOT NULL
    EXEC sp_executesql N'
        IF EXISTS (
            SELECT 1 FROM dbo.product_position_assignments
            WHERE aisle_location_id IS NOT NULL
        )
            THROW 51019,
                ''0108 rollback requires materialized assignment identity to be empty'',
                1;';
GO
IF COL_LENGTH(
    N'dbo.position_materialization_association_receipts', N'source_detection_id'
) IS NOT NULL
    EXEC sp_executesql N'
        IF EXISTS (
            SELECT 1 FROM dbo.position_materialization_association_receipts
            WHERE source_detection_id IS NOT NULL
        )
            THROW 51019,
                ''0108 rollback requires materialized receipt identity to be empty'',
                1;';
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.position_materialization_association_receipts')
      AND name = N'UQ_pmar_source_detection'
)
    DROP INDEX UQ_pmar_source_detection
        ON dbo.position_materialization_association_receipts;
GO
IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(N'dbo.position_materialization_association_receipts')
      AND name = N'FK_pmar_source_detection'
)
    ALTER TABLE dbo.position_materialization_association_receipts
        DROP CONSTRAINT FK_pmar_source_detection;
GO
IF COL_LENGTH(
    N'dbo.position_materialization_association_receipts', N'source_detection_id'
) IS NOT NULL
    ALTER TABLE dbo.position_materialization_association_receipts
        DROP COLUMN source_detection_id;
GO

IF COL_LENGTH(N'dbo.product_position_assignments', N'aisle_location_id') IS NOT NULL
BEGIN
    IF EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.product_position_assignments')
          AND name = N'CK_ppa_automatic_evidence'
    )
        ALTER TABLE dbo.product_position_assignments
            DROP CONSTRAINT CK_ppa_automatic_evidence;

    IF EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.product_position_assignments')
          AND name = N'CK_ppa_unassigned_position_null'
    )
        ALTER TABLE dbo.product_position_assignments
            DROP CONSTRAINT CK_ppa_unassigned_position_null;

    ALTER TABLE dbo.product_position_assignments WITH CHECK
        ADD CONSTRAINT CK_ppa_automatic_evidence CHECK (
            assignment_status <> 'ASSIGNED_AUTOMATIC'
            OR (position_label_id IS NOT NULL AND source_detection_id IS NOT NULL)
        );

    ALTER TABLE dbo.product_position_assignments WITH CHECK
        ADD CONSTRAINT CK_ppa_unassigned_position_null CHECK (
            assignment_status = 'ASSIGNED_AUTOMATIC' OR position_label_id IS NULL
        );
END
GO

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.product_position_assignments')
      AND name = N'IX_ppa_aisle_location'
)
    DROP INDEX IX_ppa_aisle_location ON dbo.product_position_assignments;
GO
IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID(N'dbo.product_position_assignments')
      AND name = N'FK_ppa_aisle_location'
)
    ALTER TABLE dbo.product_position_assignments DROP CONSTRAINT FK_ppa_aisle_location;
GO
IF COL_LENGTH(N'dbo.product_position_assignments', N'aisle_location_id') IS NOT NULL
    ALTER TABLE dbo.product_position_assignments DROP COLUMN aisle_location_id;
GO
