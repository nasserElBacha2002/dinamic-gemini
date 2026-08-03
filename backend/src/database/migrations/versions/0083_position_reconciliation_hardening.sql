/*
  0083_position_reconciliation_hardening.sql

  Enforce valid and internally consistent Phase 4 assignment rows.
*/

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_assignment_status CHECK (
    assignment_status IN (
        'ASSIGNED_AUTOMATIC',
        'UNASSIGNED_NO_PREVIOUS_POSITION',
        'UNASSIGNED_AFTER_AMBIGUOUS_POSITION',
        'UNASSIGNED_INVALID_POSITION',
        'UNASSIGNED_UNORDERED_ASSET',
        'SKIPPED_NO_ITEM_RESULT'
    )
);
GO

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_assignment_source CHECK (
    assignment_source IS NULL OR assignment_source = 'AUTOMATIC'
);
GO

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_automatic_evidence CHECK (
    assignment_status <> 'ASSIGNED_AUTOMATIC'
    OR (position_label_id IS NOT NULL AND source_detection_id IS NOT NULL)
);
GO

ALTER TABLE dbo.product_position_assignments WITH CHECK
ADD CONSTRAINT CK_ppa_unassigned_position_null CHECK (
    assignment_status = 'ASSIGNED_AUTOMATIC' OR position_label_id IS NULL
);
GO
