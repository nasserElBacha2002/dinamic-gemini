-- Phase C9 — Remove deprecated inventory-level visual references table.
-- Safe only after C5.1 strict dry-run confirms zero rows (see audit/raw/phase-c5-legacy-reference-migration-summary.json).

IF OBJECT_ID('inventory_visual_references', 'U') IS NOT NULL
BEGIN
    IF EXISTS (SELECT 1 FROM inventory_visual_references)
        THROW 51029, 'Cannot drop inventory_visual_references: table is not empty.', 1;

    DROP TABLE inventory_visual_references;
END;
GO
