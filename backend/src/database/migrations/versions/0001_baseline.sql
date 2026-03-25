-- Baseline marker migration for the current production schema snapshot.
-- IMPORTANT:
-- - This migration is intentionally metadata-only.
-- - Existing environments should run the historical bootstrap (`src/database/schema.sql`)
--   before this migration marker is applied.
-- - New incremental migrations must be added as new files (0002_*.sql, 0003_*.sql, ...).

SELECT 1 AS baseline_marker;
