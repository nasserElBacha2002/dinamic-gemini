# Position association — P0 server evidence pack

**Status:** `BLOCKED_PENDING_SERVER_EXECUTION`  
**Date:** 2026-08-05  
**Scope:** Diagnostic only — no P2 code changes.  
**Evidence status:** templates only — **no server results have been executed or invented**.

## Case

| Field | Value |
|-------|-------|
| inventory_id | `9199198e-e694-48a5-9004-1ddc2e5701c2` |
| aisle_id | `059b7acd-f945-481f-abe2-04457b3df91b` |
| jobs | `7a6f1273-d9d4-4f69-967d-5a1681a6769d`, `18879293-3dc1-49c1-85ce-da2e165b87df` |
| priority assets | `31b68d93-596f-4c00-b066-1c75185de584`, `03a4b9ff-708d-409f-9771-937cb1cf2a79` |

## Schema sources (repo — confirmed from migrations)

| Concern | Table / column | Migration |
|---------|----------------|-----------|
| Job↔asset order | `dbo.job_source_assets` (`sequence_number`, `position_order`, `source_asset_id`, `job_id`) | `0045_job_source_assets.sql` |
| Asset filename on job link | `dbo.job_source_assets.original_filename` | `0046_job_source_assets_original_filename.sql` |
| Inventory scope of aisle jobs | `dbo.aisles.inventory_id` + `inventory_jobs.target_type='aisle'` / `target_id` | schema + aisle FK |
| Position label detections | `dbo.image_position_label_detections` (`inventory_id`, `detection_status`, `public_identifier`, …) | `0080_image_position_label_detections.sql` |
| Client labels catalog | `dbo.client_position_labels` | `0079_client_position_labels.sql` |
| Product↔label assignments | `dbo.product_position_assignments` | `0082_position_reconciliation.sql` |

Raw decoded symbol text is **not** a first-class SQL column on detections (only `raw_payload_hash`, `public_identifier`, `metadata_json`). Symbol payloads live in job `execution_log.jsonl` under `output/<job_id>/run/` when persisted on the host volume.

## Why this environment cannot fill results

Cursor agent has **no SSH** to `dinamicsystems` / OpenCloud SQL. Commands below are **command templates**. Do not treat them as executed evidence.

## Command templates (run on the server)

```bash
cd /opt/dinamic/dinamic-gemini/backend

# Prefer docker-compose exec into api (has app env / pyodbc)
docker-compose exec -T api python3 - <<'PY'
print("Use SQL blocks below via sqlcmd or your usual inventory-api DB client")
PY
```

Host volume logs (if present after chown fix):

```bash
ls -la /opt/dinamic/dinamic-gemini/data/output/7a6f1273-d9d4-4f69-967d-5a1681a6769d/run/ 2>/dev/null
ls -la /opt/dinamic/dinamic-gemini/data/output/18879293-3dc1-49c1-85ce-da2e165b87df/run/ 2>/dev/null
# Then: rg -n '31b68d93|03a4b9ff|POSITION_LABEL|position_statuses' \
#   /opt/dinamic/dinamic-gemini/data/output/<job_id>/run/execution_log.jsonl
```

## SQL templates (SQL Server) — not executed

These queries use confirmed schema names. They are **templates pending server execution**, not “exact executed SQL”.

### 1) Ordered assets for both jobs (scoped by `@inv` via aisle)

```sql
DECLARE @inv VARCHAR(36) = '9199198e-e694-48a5-9004-1ddc2e5701c2';
DECLARE @aisle VARCHAR(36) = '059b7acd-f945-481f-abe2-04457b3df91b';

SELECT
  j.id AS job_id,
  jsa.source_asset_id AS asset_id,
  jsa.original_filename,  -- confirmed: job_source_assets.original_filename (0046)
  jsa.sequence_number,
  jsa.position_order,
  jsa.created_at AS link_created_at
FROM dbo.inventory_jobs j
INNER JOIN dbo.aisles a
  ON a.id = j.target_id
 AND j.target_type = N'aisle'
 AND a.inventory_id = @inv
INNER JOIN dbo.job_source_assets jsa
  ON jsa.job_id = j.id
WHERE j.id IN (
  '7a6f1273-d9d4-4f69-967d-5a1681a6769d',
  '18879293-3dc1-49c1-85ce-da2e165b87df'
)
AND j.target_id = @aisle
ORDER BY j.id, COALESCE(jsa.sequence_number, jsa.position_order), jsa.source_asset_id;
```

### 2) Detections for priority assets + catalog JOIN (both jobs, `@inv`)

```sql
DECLARE @inv VARCHAR(36) = '9199198e-e694-48a5-9004-1ddc2e5701c2';

SELECT
  d.job_id,
  d.source_asset_id AS asset_id,
  d.sequence_number,
  d.detection_status,
  d.signature_status,
  d.public_identifier,
  d.position_label_id,
  d.position_name_snapshot,
  d.payload_version,
  d.raw_payload_hash,
  d.metadata_json,
  d.created_at,
  d.updated_at,
  cpl.id AS catalog_label_id,
  cpl.name AS catalog_label_name,
  cpl.status AS catalog_label_status,
  cpl.client_id AS catalog_client_id
FROM dbo.image_position_label_detections d
LEFT JOIN dbo.client_position_labels cpl
  ON cpl.public_identifier = d.public_identifier
 AND cpl.client_id = (
       SELECT i.client_id
       FROM dbo.inventories i
       WHERE i.id = @inv
     )
WHERE d.inventory_id = @inv
AND d.job_id IN (
  '7a6f1273-d9d4-4f69-967d-5a1681a6769d',
  '18879293-3dc1-49c1-85ce-da2e165b87df'
)
AND d.source_asset_id IN (
  '31b68d93-596f-4c00-b066-1c75185de584',
  '03a4b9ff-708d-409f-9771-937cb1cf2a79'
)
ORDER BY d.job_id, d.source_asset_id, d.created_at;
```

### 3) Inventory client (for catalog client check)

```sql
DECLARE @inv VARCHAR(36) = '9199198e-e694-48a5-9004-1ddc2e5701c2';

SELECT id, client_id
FROM dbo.inventories
WHERE id = @inv;
```

### 4) Active assignments for product results (both jobs, scoped by `@inv`)

```sql
DECLARE @inv VARCHAR(36) = '9199198e-e694-48a5-9004-1ddc2e5701c2';

SELECT
  a.job_id,
  a.result_id,
  a.source_asset_id,
  a.sequence_number,
  a.assignment_status,
  a.assignment_reason,
  a.position_label_id,
  a.position_name_snapshot,
  a.is_active
FROM dbo.product_position_assignments a
WHERE a.inventory_id = @inv
AND a.job_id IN (
  '7a6f1273-d9d4-4f69-967d-5a1681a6769d',
  '18879293-3dc1-49c1-85ce-da2e165b87df'
)
AND a.is_active = 1
ORDER BY a.job_id, a.sequence_number, a.source_asset_id;
```

## Expected mapping (code → P0 columns)

| Question | Where answered |
|----------|----------------|
| detection_status | `image_position_label_detections.detection_status` |
| POSITION_LABEL_UNRESOLVED condition | CODE_SCAN meta: position candidates present, none in `{VALID, SIGNATURE_VALIDATION_SKIPPED}` (`code_scan_processing_strategy.py`) |
| Parser | `PositionLabelPayloadParser` + `PositionLabelValidationService` + `PositionLabelResolver` |
| Lookup key | `public_identifier` / `label_id` in JSON payload → `client_position_labels` (JOIN above) |
| active_position at product time | Only if a prior frame had `VALID` / `LEGACY_UNSIGNED_REQUIRES_REVIEW` with `position_label_id` in reconciler order |

## Results (to fill after server run)

**All cells remain PENDING until queries are actually executed.**

### Nine-asset table

| seq | asset_id | filename | job_id | detection_status | error_code (log) | position_label_id | assignment outcomes |
|-----|----------|----------|--------|------------------|------------------|-------------------|---------------------|
| … | … | … | … | **PENDING** | … | … | … |

### Priority unresolved detail

| Field | 31b68d93-… | 03a4b9ff-… |
|-------|------------|------------|
| detection_status | PENDING | PENDING |
| public_identifier | PENDING | PENDING |
| signature_status | PENDING | PENDING |
| metadata_json | PENDING | PENDING |
| label exists in catalog? | PENDING | PENDING |
| same client as inventory? | PENDING | PENDING |

## Cause (only after rows filled)

**Do not declare root cause while tables remain PENDING.**

- Demonstrated: —  
- Not yet demonstrable: exact `detection_status` / whether label missing vs signature vs legacy payload.

## P2 recommendation gate

| If detection_status is… | P2 direction |
|-------------------------|--------------|
| `LABEL_NOT_FOUND` | Ensure client labels exist / print matching `label_id` |
| `INVALID_SIGNATURE` / `UNKNOWN_KEY_VERSION` | Align HMAC secret / key_version on OpenCloud |
| `UNSUPPORTED_LEGACY_PAYLOAD` | Migrate printers to Phase 3 client labels |
| `MISSING_SIGNATURE` without LEGACY path | Unsigned label not in catalog as ACTIVE UNSIGNED |
| `VALID` but products unassigned | P2 = reconciliation / sequence_number bug (propagation) |
| Rows empty | Persistence disabled or wrong job_id — check env + logs |

## P1 note

UI false “Evento de transición…” is corrected in code independently of this P0 pack (see corrections-scoped P1). P2 association algorithm must not ship without real `evidence_status` from this pack.
