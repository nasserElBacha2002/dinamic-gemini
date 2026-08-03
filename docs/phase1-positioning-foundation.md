# Phase 1 — Ordered capture & positioning foundation

## Separation of label concepts

> La etiqueta del ítem identifica al ítem y no contiene su posición.

> La etiqueta de posicionamiento identifica una ubicación física y se genera de manera independiente desde Dinamic Inventory.

> La relación ítem–posición será calculada en una fase posterior utilizando el orden lógico de captura.

Physical locations are modeled as **`aisle_locations`** (not CV `positions`). Emitted positioning labels are **`aisle_location_labels`** with payload discriminator `DINAMIC_POSITION`. Signature status is `NOT_IMPLEMENTED` in this phase (no fake crypto).

## Logical capture order (source of truth)

```text
ordered_capture_session_id + sequence_number + client_image_id (upload_client_file_id)
```

- Assigned on mobile **before** concurrent uploads and persisted locally (`capture_photos.sequence_number`).
- Backend persists the client sequence; it does **not** derive new-session order from `uploaded_at`, filename, or DB ids.
- `job_source_assets.position_order` is an alias of `sequence_number` when CLIENT_ASSIGNED (must not diverge).
- Legacy aisles without ordered sessions keep `LEGACY_IMAGE_ORDER_ENABLED` path (explicitly non-authoritative).

## Session states

`OPEN` → `UPLOADING` → `SEALED` → `PROCESSING` → `COMPLETED` | `FAILED`

- Seal: `POST /api/v3/inventories/ordered-capture-sessions/{id}/seal`
- Process requires `SEALED` for sessions that carry `CLIENT_ASSIGNED` assets.

## Feature flags

| Env | Default | Role |
|-----|---------|------|
| `ORDERED_CAPTURE_SESSIONS_ENABLED` | true | Create/seal APIs |
| `CLIENT_SEQUENCE_REQUIRED` | false | Future: reject uploads without sequence |
| `AISLE_LOCATION_DOMAIN_ENABLED` | true | Location CRUD |
| `AISLE_LOCATION_LABELS_ENABLED` | true | Label issue/list/invalidate |
| `LEGACY_IMAGE_ORDER_ENABLED` | true | Allow process without ordered session |

## Migrations / bootstrap

- Forward: `backend/src/database/migrations/versions/0074_ordered_capture_sessions_and_positioning_foundation.sql`
- Clean install: same DDL appended to `backend/src/database/schema.sql`
- Mobile: SQLite migration v19 (`sequence_number`, `backend_ordered_capture_session_id`)

## Out of scope (later phases)

- QR/PDF/PNG render and print
- Visual detection of positioning labels
- Item↔position reconciliation
- Adding position fields to item-label contracts
