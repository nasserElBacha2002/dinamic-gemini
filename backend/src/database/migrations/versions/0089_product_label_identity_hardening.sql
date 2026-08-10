/*
  0089_product_label_identity_hardening.sql

  Corrective constraints for D1 product labels (0088 already created tables).
  - Tighten issued quantity / label_id length
  - Document: no FK product_records.label_id → issued (legacy NULL; scan may precede sync)
  - Document: no FK on inventory_counted first_* ids (insert order: claim before product_record
    is created with preallocated UUID; claim row may outlive product on rollback races —
    claim and product share the same UoW TX so orphan claims are avoided by rollback)

  Rollback: 0089_product_label_identity_hardening.down.sql
*/

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_quantity')
    ALTER TABLE dbo.issued_product_labels DROP CONSTRAINT CK_issued_product_labels_quantity;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_quantity_range'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_quantity_range
        CHECK (quantity BETWEEN 1 AND 99999999);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_label_id_len'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_label_id_len
        CHECK (LEN(label_id) = 10);
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_checksum_len'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_checksum_len
        CHECK (LEN(checksum) = 1);
GO
