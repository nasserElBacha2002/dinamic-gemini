-- DIN-508 — literal aisle-code equivalence under dbo.aisles.code collation (read-only).
SET NOCOUNT ON;

SELECT
    CASE WHEN CAST(N'A01' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
              = CAST(N'a01' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
         THEN 1 ELSE 0 END AS equiv_a01_a01_lower;

SELECT
    CASE WHEN CAST(N'  A01  ' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
              = CAST(N'a01' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
         THEN 0 ELSE 1 END AS padded_not_equal_without_trim;

SELECT
    CASE WHEN CAST(N'Pasillo_A_04' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
              = CAST(N'pasillo_a_04' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
         THEN 1 ELSE 0 END AS equiv_pasillo_case;

SELECT
    CASE WHEN CAST(N'Café' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
              = CAST(N'CAFE' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
         THEN 1 ELSE 0 END AS equiv_cafe_accent;

SELECT
    CASE WHEN CAST(N'Straße' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
              = CAST(N'STRASSE' AS VARCHAR(64)) COLLATE SQL_Latin1_General_CP1_CI_AS
         THEN 1 ELSE 0 END AS equiv_german_eszett;