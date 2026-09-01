# Mobile offline-first Phase 1 — local catalog design

## Local schema (SQLite v29)

| Table | Purpose |
|-------|---------|
| `local_inventories` | Durable inventory list (`id`, `client_id`, `name`, `status`, `active`, counts, timestamps) |
| `local_aisles` | Aisles per inventory (`inventory_id` + `id` PK) |
| `local_client_suppliers` | Supplier catalog per client (`client_id` + `id` PK) |
| `catalog_sync_meta` | Singleton row: `catalog_revision`, `last_synced_at`, counts |

Reused (unchanged):

- `offline_recognition_profiles`
- `offline_aisle_recognition_config`
- `offline_recognition_sync_meta`

Operational data (drafts, captures, uploads) is never deleted by catalog sync.

## Startup flow

```text
App.tsx
  → createAppServices() [SQLite open + migration]
  → connectivity.getState()
  → auth.restore(connectivity)
      online → GET /auth/me → cache user in SecureStore
      offline / network failure → cached session user if token exists
  → catalog.bootstrap(mode)
      hydrate counts from SQLite (non-blocking)
      emit mobile.catalog.hydrated
      if online → background catalog.syncCatalog()
  → render inventories screen from SQLite immediately
```

Auth without prior session + offline → login screen (out of scope for virgin provisioning).

## Sync flow

```text
catalog.syncCatalog()
  → fetch v3 inventories (paginated)
  → fetch aisles per inventory
  → fetch suppliers per client_id
  → compute catalog_revision (sha256 canonical hash)
  → if revision == local → no-op
  → else replaceCatalogSnapshot() in one SQLite transaction
      soft-retire (active=0) then upsert active rows
  → for each inventory: offlineRecognitionSync.syncInventory()
```

Triggers:

- App bootstrap when online
- Connectivity offline → online
- Manual “Sincronizar” on Inventories screen
- Background refresh after local-first list reads (when online)

## Revision strategy

`catalog_revision` changes when any of:

- inventory id/status/updated_at/name/processing_mode
- aisle id/status/code/is_active/updated_at
- supplier id/status/name/updated_at

Excludes `generated_at` and sync timestamps.

Recognition bundles keep separate `bundle_revision` per inventory.

## Failure behavior

- Sync runs inside `withTransactionAsync` — partial writes roll back.
- Network timeout / 500 during startup: UI uses SQLite; auth uses cached user.
- Real 401 when online: session cleared per existing auth flow.
- Empty SQLite + offline: explicit empty-state message (not “backend empty”).

## Historical profiles

Pending drafts retain `recognition_profile_snapshot_json`. Active resolver reads latest synced profile from SQLite. Profile version drift for in-flight drafts is handled via snapshot, not duplicate profile rows (PK is supplier+kind per inventory).

## Readiness

`assessInventoryCatalogReadiness()`:

- `READY_OFFLINE`: inventory + suppliers + aisles + recognition bundle
- `PARTIAL`: metadata present but missing some pieces
- `NOT_READY`: no usable inventory row

Incomplete inventories do not block others.
