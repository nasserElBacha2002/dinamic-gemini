# Online aisle create materialization — root cause audit

## OLD_FLOW

`CreateAisleModal.submitCreate` awaited `AisleService.create`, then invoked `onCreated`. `AislesScreen` immediately invoked `onSelectNew`; `App` called `capture.prepareNewCapture` and changed to the capture screen. The capture session itself is persisted later by `CaptureService`, on capture start.

`AisleService.create` knew `inventoryId` and the selected `clientSupplierId`, POSTed the aisle, optionally refreshed its status, and returned the DTO. Neither the POST representation nor the refreshed DTO was written to `local_aisles`. A new aisle created after the last catalog/recognition sync therefore entered capture without a local supplier association.

## NEW_FLOW

The service boundary now enforces:

`POST -> authoritative DTO/status refresh -> validate returned supplier association -> LocalCatalogRepository.upsertRemoteAisle -> resolver readiness -> return -> UI navigation`.

The API response remains authoritative. When a supplier was requested, a response that omits or contradicts that association fails closed; the UI selection is not used to synthesize catalog identity.

## TRANSACTION / ORDERING

`upsertRemoteAisle` executes one SQLite transaction and reads the row back before resolving. It delegates to the same private `upsertRemoteAisleRow` primitive used by `replaceCatalogSnapshot`, preserving the `(inventory_id, id)` conflict behavior and the projected fields: identity, code/status, active, counters, `client_supplier_id`, timestamps, `origin=REMOTE`, and `sync_status=REMOTE_SYNCED`.

`AisleService.create` does not resolve until the write and read-back finish. The existing modal only calls `onCreated` after that promise resolves, so navigation/capture cannot precede materialization.

## FAILURE_BEHAVIOR

If backend creation succeeds but SQLite materialization fails, the service throws typed `REMOTE_AISLE_MATERIALIZATION_FAILED`; the modal displays the error and does not call `onCreated`. No backend rollback is attempted.

The authoritative response is retained in the live service by inventory/code. A user retry retries materialization/readiness only and does not issue a blind duplicate POST. This is intentionally in-memory; a process restart falls back to normal backend conflict/refresh behavior.

Structured events are emitted as `mobile.aisle.remote_materialized` and `mobile.aisle.remote_materialization_failed`, without raw label data.

## RESOLVER_AFTER_CREATE

The production resolver is injected into `AisleService`. After upsert its cache is invalidated and `resolveForAisle` runs. A missing required Supplier profile or unavailable Supplier base configuration blocks capture with `RECOGNITION_CONFIG_NOT_READY`. Valid DINAMIC sources remain valid.

No catalog sync or recognition sync is forced. When no aisle-specific recognition row exists, resolver precedence falls through to the materialized aisle's `client_supplier_id`, then ClientSupplier base sources/profiles. A later aisle configuration still has first priority.

## TEST_EVIDENCE

- Deferred-write test proves create cannot return before the local upsert.
- SQLite-write failure test proves fail-closed behavior.
- Retry test proves no duplicate POST after a partial success.
- The golden race regression now uses real `AisleService`, `LocalCatalogRepository`, `OfflineRecognitionConfigRepository`, `LocalLabelProfileResolver`, and `LocalCodeScanStrategy`, with no aisle-specific recognition row and no intervening sync.
- Golden POSITION `A04-R-02|04|RIGHT|02` produces `LOCAL_POSITION_LABEL` / `A04-R-02`.
- Golden ITEM `LPNA000184|SKU773421|24` produces `LOCAL_CODE_SCAN` / `LPNA000184` / `SKU773421` / quantity 24.
- Export contains zero `LOCAL_PENDING` rows.
- Existing resolver tests cover Supplier v10/v3, mixed sources, missing profile fail-closed, and aisle override precedence.

No migration is required. Migration v33, projection healing, revision hashing, local-only aisle behavior, and export preflight were not changed.
