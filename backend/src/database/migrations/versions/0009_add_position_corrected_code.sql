-- v3.3.4 — Persist corrected position code for manual review flow
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'corrected_position_code')
    ALTER TABLE positions ADD corrected_position_code VARCHAR(64) NULL;
GO
