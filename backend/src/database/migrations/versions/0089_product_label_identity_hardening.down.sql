/*
  0089_product_label_identity_hardening.down.sql
*/

IF EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_checksum_len'
)
    ALTER TABLE dbo.issued_product_labels DROP CONSTRAINT CK_issued_product_labels_checksum_len;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_label_id_len'
)
    ALTER TABLE dbo.issued_product_labels DROP CONSTRAINT CK_issued_product_labels_label_id_len;
GO

IF EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_quantity_range'
)
    ALTER TABLE dbo.issued_product_labels DROP CONSTRAINT CK_issued_product_labels_quantity_range;
GO

-- Restore prior broad quantity check from 0088.
IF NOT EXISTS (
    SELECT 1 FROM sys.check_constraints WHERE name = N'CK_issued_product_labels_quantity'
)
    ALTER TABLE dbo.issued_product_labels
        ADD CONSTRAINT CK_issued_product_labels_quantity CHECK (quantity >= 1);
GO
