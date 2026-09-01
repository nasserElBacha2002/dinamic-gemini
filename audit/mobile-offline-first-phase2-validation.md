# Phase 2 validation — Mobile offline-first automatic sync

## Commands

| Command | Result |
|---------|--------|
| `npm run typecheck` | PASS |
| `npm run test:core` | PASS (317 tests) |
| `npm run test:services` | PASS (241 tests) |

### Targeted suites

| Suite | Result |
|-------|--------|
| catalogSyncService | PASS (15 tests incl. coordinator) |
| catalogRevision | PASS |
| catalogColdStart | PASS |
| catalogReadiness | PASS |
| offlineRecognitionSync | PASS |
| databaseMigrations | PASS (v30) |
| inventoryService | PASS |
| aisleService | PASS |

## Acceptance criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Local-first preserved | PASS |
| 2 | Sync never blocks startup | PASS |
| 3 | Bootstrap online triggers sync | PASS |
| 4 | Reconnect triggers sync | PASS |
| 5 | Foreground sync with throttle | PASS |
| 6 | Manual sync works | PASS |
| 7 | Single-flight | PASS |
| 8–11 | New inventory/supplier/aisle + changes | PASS (service + repository tests) |
| 12–14 | Profile-only + source changes | PASS (recognition independent of catalog revision) |
| 15 | Independent bundle_revision | PASS |
| 16–18 | Partial failure + retry | PASS |
| 19–20 | Historical drafts preserved | PASS (no operational table writes in sync) |
| 21 | No duplicate by name | PASS (upsert by ID) |
| 22 | Pagination | PASS |
| 23 | Order-independent hash | PASS (catalogRevision.test) |
| 24–26 | Network/500/401 behavior | PASS (catalogColdStart + authService) |
| 27 | Operational data never deleted | PASS (replaceCatalogSnapshot scope) |
| 28–30 | Typecheck + tests | PASS |
| 31 | Device E2E | UNVERIFIED |

## Status summary

```
PHASE_2_STATUS: READY_WITH_OBSERVATIONS

CATALOG_SYNC: PASS
RECOGNITION_INDEPENDENT_SYNC: PASS
PROFILE_ONLY_UPDATE: PASS
PARTIAL_FAILURE_RETRY: PASS
RECONNECT_SYNC: PASS
FOREGROUND_SYNC: PASS
MANUAL_SYNC: PASS
SINGLE_FLIGHT: PASS
PAGINATION: PASS
OPERATIONAL_DATA_PRESERVED: PASS
DEVICE_E2E: UNVERIFIED
```

## Observations

1. **Device E2E** (profile v10→v11 on real device) not executed in CI; requires manual verification with golden inventory/supplier IDs.
2. **Aisle `client_supplier_id` / profile overrides** are not in `catalog_revision` hash yet — they live in recognition bundle; aisle metadata changes that only affect recognition are picked up via independent recognition sync.
3. **v30 migration** adds sync status columns; backward compatible from v29.
