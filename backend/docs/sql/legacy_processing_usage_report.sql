-- Read-only LEGACY processing usage report (do not mutate data).
-- Run against the operational SQL Server database before tenant migration.
-- Safe to re-run; no DDL/DML.

-- 1) System / config notes: system default for NEW jobs is INTERNAL_OCR (application).
--    Historical null job modes still coerce to LEGACY_LLM on read.

-- 2) Clients with LEGACY default
SELECT c.id AS client_id, c.name, c.default_identification_mode
FROM clients c
WHERE UPPER(ISNULL(c.default_identification_mode, '')) IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY');

-- 3) Inventories with LEGACY
SELECT i.id AS inventory_id, i.name, i.client_id, i.identification_mode
FROM inventories i
WHERE UPPER(ISNULL(i.identification_mode, '')) IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY');

-- 4) Aisles with LEGACY
SELECT a.id AS aisle_id, a.inventory_id, a.code, a.identification_mode
FROM aisles a
WHERE UPPER(ISNULL(a.identification_mode, '')) IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY');

-- 5) Jobs by window (30 / 60 / 90 days) — requested mode vs executed strategy
SELECT
  CASE
    WHEN j.created_at >= DATEADD(day, -30, SYSUTCDATETIME()) THEN '30d'
    WHEN j.created_at >= DATEADD(day, -60, SYSUTCDATETIME()) THEN '60d'
    WHEN j.created_at >= DATEADD(day, -90, SYSUTCDATETIME()) THEN '90d'
    ELSE 'older'
  END AS window_bucket,
  j.identification_mode AS requested_mode,
  j.execution_strategy AS executed_strategy,
  COUNT(*) AS job_count
FROM jobs j
WHERE j.job_type = 'process_aisle'
  AND (
    UPPER(ISNULL(j.identification_mode, '')) IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY')
    OR UPPER(ISNULL(j.execution_strategy, '')) IN ('LEGACY_LLM', 'LEGACY_LLM_TEMPORARY')
  )
  AND j.created_at >= DATEADD(day, -90, SYSUTCDATETIME())
GROUP BY
  CASE
    WHEN j.created_at >= DATEADD(day, -30, SYSUTCDATETIME()) THEN '30d'
    WHEN j.created_at >= DATEADD(day, -60, SYSUTCDATETIME()) THEN '60d'
    WHEN j.created_at >= DATEADD(day, -90, SYSUTCDATETIME()) THEN '90d'
    ELSE 'older'
  END,
  j.identification_mode,
  j.execution_strategy
ORDER BY window_bucket, job_count DESC;

-- Reversible tenant migration (manual; do NOT run automatically):
-- UPDATE clients SET default_identification_mode = 'INTERNAL_OCR'
--   WHERE default_identification_mode = 'LEGACY_LLM' AND id = @client_id;
-- UPDATE inventories SET identification_mode = 'INTERNAL_OCR'
--   WHERE identification_mode = 'LEGACY_LLM' AND client_id = @client_id;
-- UPDATE aisles SET identification_mode = 'INTERNAL_OCR'
--   WHERE identification_mode = 'LEGACY_LLM' AND inventory_id IN (...);
-- Rollback: restore previous values from a backup table taken before UPDATE.
