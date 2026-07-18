# Aisle identification mode — Phase 1

## Purpose

Introduce a typed **aisle identification mode** (how a pasillo should be identified) with
hierarchical configuration and an **immutable job snapshot**, without changing productive
LLM processing yet.

This is **independent** of `InventoryProcessingMode` (`production` | `test`).

## Modes

| Value | Meaning |
|-------|---------|
| `CODE_SCAN` | Future internal QR/barcode processing |
| `INTERNAL_OCR` | Future internal visual/OCR processing |
| `LEGACY_LLM` | Current external LLM hybrid pipeline |

There is no `AUTO` value.

## Inheritance

```text
Request (process body, job-only)
  → Aisle.identification_mode
    → Inventory.identification_mode
      → Client.default_identification_mode
        → SYSTEM_DEFAULT = LEGACY_LLM
```

Null at any config level means “inherit”. The only resolver is
`resolve_aisle_identification_mode` in `src/domain/aisle_identification/`.

## Job snapshot (immutable)

On `POST .../aisles/{id}/process`, new jobs persist:

- `identification_mode`
- `identification_mode_source` (`REQUEST` | `AISLE` | `INVENTORY` | `CLIENT` | `SYSTEM_DEFAULT`)
- `configuration_snapshot_version` (currently `1`)
- `execution_strategy` (`LEGACY_LLM` or `LEGACY_LLM_TEMPORARY`)

Existing job fields already frozen at create time remain: `provider_name`, `model_name`,
`prompt_key`, `prompt_version` (when set). Client profile keys / fallback order are not
invented in Phase 1 (nullable contracts deferred).

Changing client/inventory/aisle config after create **must not** change an existing job.
The worker reads the job snapshot; it does not re-resolve mutable config.

Historical jobs (pre-migration) are backfilled / coerced to
`LEGACY_LLM` + `LEGACY_MIGRATION`.

## Feature flag

```bash
AISLE_IDENTIFICATION_PIPELINE_ENABLED=false  # default
```

- **false:** processing path stays the legacy LLM pipeline; snapshots still persist.
- **true (Phase 1):** same legacy pipeline for all modes; non-`LEGACY_LLM` jobs are labeled
  `execution_strategy=LEGACY_LLM_TEMPORARY` so operators know barcode/OCR are not active yet.

Disabling the flag does not rewrite existing job snapshots.

## API

### Process

```http
POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process
```

Optional body field:

```json
{ "identification_mode": "CODE_SCAN" }
```

Additive response fields: `identification_mode`, `identification_mode_source`,
`execution_strategy`, `configuration_snapshot_version`.

### Config surfaces

Client / inventory / aisle responses include:

- `identification_mode` — local configured value (`null` = inherit)
- `effective_identification_mode`
- `identification_mode_source`

PATCH inventory/aisle (with existing name/code) and PATCH client accept
`identification_mode`; send JSON `null` to clear an override (`model_fields_set`).

## Phase 1 execution map

```text
CODE_SCAN    → LEGACY_LLM_TEMPORARY (when flag on) / LEGACY_LLM (flag off)
INTERNAL_OCR → LEGACY_LLM_TEMPORARY (when flag on) / LEGACY_LLM (flag off)
LEGACY_LLM   → LEGACY_LLM
```

## Migration

`0049_aisle_identification_mode.sql` — additive columns on `clients`, `inventories`,
`aisles`, `inventory_jobs` + backfill. Rollback: drop the new columns (no data loss on
legacy processing columns).

## Out of scope (later phases)

Orchestrators, per-image strategies, real CODE_SCAN/OCR in the job worker, ProcessingAttempt,
fallback-by-image, prompt/profile migration.
