# Mobile offline-first — Phase 2 sync design

## Goal

Keep the local SQLite catalog (inventories, aisles, suppliers) and recognition bundles updated automatically while online, without blocking startup or requiring manual preparation per inventory.

## Architecture

```
App bootstrap / reconnect / foreground / manual / login
        ↓
CatalogSyncCoordinator  (throttle + trigger routing)
        ↓
CatalogSyncService      (single-flight syncInFlight)
        ↓
fetch remote snapshot (HTTP, all pages)
        ↓
compare catalog_revision
        ↓
replaceCatalogSnapshot (SQLite transaction)  [if changed]
        ↓
recognitionSync.syncInventory() per inventory  [always]
        ↓
record sync meta + observability
```

## Triggers

| Trigger | Source | Throttle | Notes |
|---------|--------|----------|-------|
| `bootstrap` | `catalog.bootstrap()` after auth restore | Yes | Non-blocking `void` |
| `reconnect` | `connectivity.subscribe(online)` | No | Forces sync after offline→online |
| `login` | `App.tsx` after successful login | No | Non-blocking |
| `foreground` | `AppState` background→active | Yes | 60s minimum interval |
| `screen_refresh` | InventoriesScreen load / pull-to-refresh | Yes | Local-first UI, background sync |
| `manual` | InventoriesScreen “Sincronizar” | No | Respects single-flight |

Central constant: `CATALOG_AUTO_SYNC_MIN_INTERVAL_MS = 60_000`.

## Single-flight

`CatalogSyncService.syncInFlight` ensures concurrent triggers share one execution. The coordinator delegates to the service; duplicate manual + reconnect + foreground calls await the same promise.

## Throttling

Auto triggers (`bootstrap`, `foreground`, `screen_refresh`) skip when `lastSuccessfulSyncAt` is within 60 seconds.

Bypass throttle: `manual`, `reconnect`, `login`, or explicit `{ force: true }`.

## Revision domains (independent)

| Revision | Scope | Computed by |
|----------|-------|-------------|
| `catalog_revision` | inventories, aisles, suppliers metadata | `computeCatalogRevision()` — order-independent SHA-256 |
| `bundle_revision` | ITEM/POSITION recognition config | Backend; checked in `OfflineRecognitionSyncService` |

**Invariant:** unchanged `catalog_revision` must NOT skip recognition sync. Recognition always runs per inventory; bundle revision decides download vs skip.

## Catalog sync result statuses

| Status | Meaning |
|--------|---------|
| `SUCCESS` | Catalog and/or recognition updated |
| `NO_CHANGES` | Same catalog revision; all recognition bundles unchanged |
| `PARTIAL` | Catalog OK; one or more recognition inventories failed |
| `FAILED` | Fetch or catalog replace failed; prior SQLite preserved |
| `SKIPPED_OFFLINE` | No network |
| `SKIPPED_THROTTLE` | Auto sync suppressed by policy |

## Partial failure & retry

- Recognition failures per inventory do not abort others (best effort).
- Global status `PARTIAL`; prior catalog snapshot remains committed.
- Next sync retries recognition even when `catalog_revision` unchanged.

## Soft retirement

Full snapshot replace:

1. Mark all current rows `active = 0`
2. Upsert remote entities with `active = 1`
3. Historical rows (drafts, captures) untouched

Removed/inactive remote inventories and suppliers remain in SQLite but are not offered for new operations.

## Sync meta (SQLite v30)

`catalog_sync_meta` stores:

- `catalog_revision`
- `last_synced_at`
- `last_sync_attempt_at`
- `last_successful_sync_at`
- `last_sync_status`
- counts (inventory, supplier, aisle)

## Observability events

Catalog: `sync_started`, `remote_fetched`, `snapshot_replaced`, `sync_no_changes`, `sync_partial`, `sync_completed`, `sync_failed`

Recognition: `sync_started`, `sync_completed`, `sync_skipped`, `sync_failed`

Safe metadata only (ids, counts, revision, duration_ms).

## UI (InventoriesScreen)

- “Sincronizando…” while manual/background sync active
- “Última sincronización: HH:MM” from `last_successful_sync_at`
- Error: “No se pudo actualizar. Se muestran datos guardados.”
- Screen never blocked; local SQLite always shown first

## Readiness

Per-inventory readiness (`catalogReadiness.ts`) unchanged: `READY_OFFLINE`, `PARTIAL`, `NOT_READY`. New inventory with failed recognition appears as `PARTIAL`.

## Out of scope (Phase 2)

Offline inventory/aisle creation, bidirectional sync, push/WebSocket background workers, delta sync, OS-level background jobs when app is killed.
