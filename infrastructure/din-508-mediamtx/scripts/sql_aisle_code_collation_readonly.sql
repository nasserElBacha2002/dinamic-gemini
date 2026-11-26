-- DIN-508 Phase 2 — read-only collation / aisle code samples (SQL Server)
SET NOCOUNT ON;

SELECT
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.collation_name
FROM sys.columns c
JOIN sys.types t ON c.user_type_id = t.user_type_id
WHERE c.object_id = OBJECT_ID(N'dbo.aisles')
  AND c.name = N'code';

SELECT
    i.name AS index_name,
    i.is_unique,
    COL_NAME(ic.object_id, ic.column_id) AS column_name,
    c.collation_name
FROM sys.indexes i
JOIN sys.index_columns ic
    ON i.object_id = ic.object_id AND i.index_id = ic.index_id
JOIN sys.columns c
    ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = OBJECT_ID(N'dbo.aisles')
  AND i.name = N'UQ_aisles_inventory_code';

SELECT TOP (20)
    inventory_id,
    code,
    DATALENGTH(code) AS code_bytes,
    LEN(code) AS code_len,
    CASE WHEN code = LTRIM(RTRIM(code)) THEN 1 ELSE 0 END AS trimmed_match
FROM dbo.aisles
ORDER BY created_at DESC;

-- Case and whitespace sensitivity probes (read-only)
SELECT COUNT(*) AS exact_match_a03
FROM dbo.aisles
WHERE code = N'A-03';

SELECT COUNT(*) AS upper_match_a03
FROM dbo.aisles
WHERE code = N'a-03';

SELECT COUNT(*) AS padded_match
FROM dbo.aisles
WHERE code = N' A-03 '