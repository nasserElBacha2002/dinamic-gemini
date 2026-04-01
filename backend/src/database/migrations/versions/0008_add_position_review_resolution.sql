-- v3.3.3 — Persist terminal operator review resolution for positions
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('positions') AND name = 'review_resolution')
    ALTER TABLE positions ADD review_resolution VARCHAR(32) NULL;
GO
