# Phase 4 — Preliminary detection sync — implementation report

**Status:** `IMPLEMENTED_WITH_LIMITATIONS`

## Architecture

```text
local CODE_SCAN draft (SQLite)
  → upload image (unchanged)
  → asset confirmed (backend_asset_id)
  → PUT .../preliminary-detections/{draft_id}
  → mobile_preliminary_detections (separate table)
  → POST /process (unchanged, authoritative)
```

Local drafts remain diagnostic. The server pipeline and positions are never updated by this endpoint.

## Endpoint

`PUT /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}`

- Auth: same v3 admin dependency as other inventory routes
- Flag: `SERVER_PRELIMINARY_DETECTION_INGEST` (default `false`) → 404 when off
- Use case: `UpsertPreliminaryDetectionUseCase`
- Persistence: `mobile_preliminary_detections` (migration `0062`)

## Contract

Versioned schema `schema_version: "1"`. No raw payload, image bytes, local paths, or tenant IDs from the client as authoritative. Inventory/aisle/company scope is derived from the route + asset ownership.

## Persistence

Table `mobile_preliminary_detections` with:

- `UNIQUE(draft_id)`
- `UNIQUE(client_file_id, detector_version, parser_version, prepared_asset_sha256)`
- FKs to `aisles` and `source_assets`
- Indexes on aisle/received, asset, client_file_id

## Security

- Aisle scoped to inventory
- Asset must belong to aisle
- `client_file_id` must match asset when present
- Client cannot set company/inventory/aisle as authoritative fields
- Logs omit `internal_code` / `quantity`

## Idempotency

- Same `draft_id` + same content → existing row (`duplicate=true`)
- Same `draft_id` + different content → `CONFLICT` (HTTP 409)
- Same image+versions+hash under another draft → return existing (no duplicate row)

## Mobile sync states

Separate from scan status: `NOT_READY | PENDING | SYNCING | SYNCED | RETRY_SCHEDULED | REJECTED | CONFLICT | FAILED_TERMINAL` with lease fields (migration v10).

## Retries

Network/timeout/429/5xx → backoff retry. 404 asset → retry. 422 → REJECTED. 409 → CONFLICT. 403 → FAILED_TERMINAL. Feature unavailable → temporary disable window.

## Flags

| Flag | Default |
|------|---------|
| `mobilePreliminaryDetectionSync` / `DINAMIC_FLAG_PRELIMINARY_SYNC` | false |
| `preliminaryDetectionBackgroundSync` / `DINAMIC_FLAG_PRELIMINARY_BG_SYNC` | false |
| `SERVER_PRELIMINARY_DETECTION_INGEST` | false |

## Files modified (high level)

Backend: migration 0062, entity/port/repos, use case, schemas, route, DI, settings, unit tests.  
Mobile: migration v10, draft sync methods, API + sync service, upload hook, flags, UI labels, tests.

## Limitations

1. Dedicated WorkManager worker for preliminary sync is not fully implemented; flag exists; JS sync runs after upload + bootstrap when flag is on.
2. SQL Server integration / migration upgrade against a live DB was not executed in this environment.
3. End-to-end device matrix (Samsung) not run.
4. Retention purge job (30/90 days) documented conceptually but not scheduled.
5. Concurrency stress / 100-draft load tests not run.
