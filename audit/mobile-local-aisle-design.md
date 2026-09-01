# Mobile LOCAL_ONLY Aisle — Phase 3 Design

## Identity

- UUID v4 generated via `createId()` (`crypto.randomUUID` when available).
- UUID is the durable identity for export/import (Phase 4).
- No `temp-*` or incremental local IDs.

## Origin & sync status

| Field | Values | Meaning |
|-------|--------|---------|
| `origin` | `REMOTE` \| `LOCAL` | Where the aisle row was created |
| `sync_status` | `REMOTE_SYNCED` \| `LOCAL_ONLY` | Backend confirmation lifecycle |

Operational aisle `status` (e.g. `created`) remains separate from sync status.

## SQLite

### `local_aisles` (v31)

- `client_supplier_id` — supplier association for LOCAL aisles
- `origin` — default `REMOTE` for migrated rows
- `sync_status` — default `REMOTE_SYNCED` for migrated rows
- `created_offline_at` — timestamp when created on device

### `offline_supplier_recognition_config` (v32)

Primary key: `(inventory_id, client_supplier_id)`

- `item_source` — `DINAMIC` \| `SUPPLIER` (ClientSupplier base, no aisle override)
- `position_source` — `DINAMIC` \| `SUPPLIER`
- `synced_at` — bundle sync timestamp

Populated from backend recognition bundle `suppliers[]` during `replaceBundle()`.

## Creation flow

```
AislesScreen → CreateAisleModal
  offline → AisleService.createLocal()
  online  → AisleService.create() (remote API, unchanged)
```

`createLocal`:

1. Validates inventory active + present locally
2. Rejects supplier when `inventory.client_id` is null (`INVENTORY_CLIENT_NOT_AVAILABLE_OFFLINE`)
3. Validates supplier active, same client, recognition readiness (required repo when supplier present)
4. Generates UUID, inserts row atomically (`insertLocalAisle`)
5. No HTTP calls

## Recognition resolution

### REMOTE aisle

Uses `offline_aisle_recognition_config` for that aisle:

```
aisle override → effective source → profile (if SUPPLIER) → DINAMIC default
```

### LOCAL aisle

Uses explicit ClientSupplier base source — **never** a remote aisle row as proxy:

```
local_aisles.client_supplier_id
  → offline_supplier_recognition_config (item_source / position_source)
  → profile when source=SUPPLIER
  → DINAMIC when source=DINAMIC
```

**Remote aisle overrides are never reused for a new local aisle.**

If ClientSupplier base source is unknown (no row in `offline_supplier_recognition_config`): fail closed (`RECOGNITION_CONFIG_NOT_READY` at create; `missingSupplierProfile` / `recognitionConfigNotReady` at resolve).

Profile existence alone does **not** imply `SUPPLIER` source.

## Backend bundle contract

`GET /api/v3/inventories/{id}/recognition-config` includes:

- `aisles[]` — per-aisle effective sources (includes overrides)
- `suppliers[]` — ClientSupplier base `item_source` / `position_source` (no overrides)
- `profiles[]` — active SUPPLIER extraction profiles

Mobile must not infer supplier wiring from aisle effective sources or profile presence.

## Catalog sync interaction

`replaceCatalogSnapshot`:

- Soft-retires only `origin = 'REMOTE'` aisles
- Upserts remote aisles with `origin=REMOTE`, `sync_status=REMOTE_SYNCED`
- **Never** deactivates `LOCAL_ONLY` aisles

## Upload gate

`UploadQueue.aisleAllowsRemoteUpload`:

- `sync_status === 'LOCAL_ONLY'` → block remote enqueue
- `REMOTE_SYNCED` → existing upload policy (`sessionAllowsAutoServerUpload`)
- Missing catalog when aisle context present → fail closed (block)

`mobileServerUpload` flag is **not** used for Phase 3 LOCAL_ONLY protection.

## Future export (Phase 4)

Local aisle rows include: `id`, `inventory_id`, `client_supplier_id`, `code`, captures by `aisle_id` FK (string, no remote FK).

## Observability

- `mobile.aisle.local_create_started`
- `mobile.aisle.local_created`
- `mobile.aisle.local_create_failed`

Metadata: `aisle_id`, `inventory_id`, `supplier_id`, `offline=true` (no raw barcodes).
