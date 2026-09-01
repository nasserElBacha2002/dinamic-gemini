# pruebas b — final hardening validation

Date: 2026-09-01

## ROOT_CAUSE

`CATALOG_AISLE_CLIENT_SUPPLIER_DROPPED`

`LocalCatalogRepository.replaceCatalogSnapshot()` discarded the remote aisle
`client_supplier_id` while materializing SQLite. The affected aisle then had no
Supplier context before its aisle-specific recognition mapping existed, so the
resolver selected DINAMIC and skipped Supplier validation.

## FIX_IMPLEMENTED

- Remote catalog insert/update persists `client_supplier_id`.
- `CATALOG_PROJECTION_VERSION = 1` and migration v33 add
  `catalog_sync_meta.catalog_projection_version` with upgrade default 0.
- Same-revision sync replaces the snapshot when the stored projection version
  is stale. The atomic successful replace records version 1; failures leave it
  stale for retry. The following same-revision sync skips replacement.
- Catalog revision hashing now includes aisle `client_supplier_id` for future
  association-only changes.
- `LOCAL_ONLY` rows remain outside remote retirement/overwrite operations.
- Resolver fallback uses explicit catalog Supplier base sources only when no
  aisle recognition mapping exists; aisle overrides retain precedence.
- Export preflight receives the typed resolver result and compares Supplier ID,
  ITEM source, and POSITION source independently. All four mixed-source
  combinations are supported.
- Empty semantic shells no longer become RESOLVED; detected non-semantic codes
  use `NO_VALID_CODE`.
- The golden incident-chain test uses real `LocalCatalogRepository`,
  `OfflineRecognitionConfigRepository`, and `LocalLabelProfileResolver`
  instances before scan/draft/CSV projection; resolver output is not mocked.

## MIGRATION

v33, incremental and idempotently applied through `schema_migrations`. It only
adds projection metadata; it does not update/delete aisles, captures, drafts,
profiles, authentication, or operational data.

A disposable backup of the real v32 device DB was migrated successfully:
v33 recorded, projection version initialized to 0, affected aisle/capture/draft
counts unchanged.

## TEST_RESULTS

- TypeScript: PASS.
- Scoped ESLint for every changed TypeScript file: PASS.
- Full repository ESLint: FAIL due to three pre-existing unrelated findings in
  `offlineSupplierLabelValidator.ts`, `InventoriesScreen.tsx`, and
  `LocalActivityScreen.tsx`; none is part of this correction.
- Mobile core: 36 suites / 340 tests PASS.
- Mobile services: 43 suites / 297 tests PASS.
- Mobile integration/migrations: 1 suite / 24 tests PASS.
- Previous backend targeted Supplier/package regressions: 72 tests PASS; no
  backend behavior changed in this hardening.

Coverage includes same-revision one-shot healing, LOCAL_ONLY preservation,
catalog association revision hashing, REMOTE ITEM/POSITION override precedence,
mixed-source preflight, golden v10/v3 validation, semantic draft persistence,
and zero-pending CSV projection.

## DEVICE_E2E

UNVERIFIED end-to-end.

The corrected bundle was loaded on the connected physical Samsung without
clearing storage. Migration v33 ran on the existing DB at
`2026-09-01T18:47:27.831Z`, leaving projection version 0 as intended before the
healing sync. A read-only recopy confirmed the affected aisle was still the
pre-fix NULL association. The app then required a fresh login, and credentials
were not available, so an authenticated catalog sync, new physical captures,
and ZIP export could not be completed. Device storage was not reset or manually
patched.

## FINAL_STATUS_MATRIX

| Check | Status |
|---|---|
| CATALOG_SUPPLIER_PERSISTENCE | PASS |
| EXISTING_DEVICE_DATA_HEALING | PASS (automated + real v32→v33 migration; live authenticated sync blocked) |
| SAME_REVISION_HEALING | PASS |
| LOCAL_ONLY_PRESERVATION | PASS |
| REMOTE_OVERRIDE_PRECEDENCE | PASS |
| MIXED_SOURCE_PREFLIGHT | PASS |
| GOLDEN_ITEM | PASS |
| GOLDEN_POSITION | PASS |
| LOCAL_PENDING_COUNT | 0 |
| TYPECHECK | PASS |
| TESTS | PASS |
| DEVICE_E2E | UNVERIFIED |

## KNOWN_LIMITATIONS

Completing physical E2E requires login credentials, then manual sync, two new
golden captures, and export. Historical snapshots remain immutable by design.
