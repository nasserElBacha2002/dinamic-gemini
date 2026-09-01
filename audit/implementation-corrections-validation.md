# Supplier offline import/export — implementation corrections validation

Date: 2026-09-01  
Scope: Mobile CSV export + backend local CSV materialization (supplier segmented profiles)

## Status matrix

| Criterion | Status | Notes |
|-----------|--------|-------|
| SUPPLIER_IMPORT_PROFILE_RESOLUTION | **PARTIAL** | Mobile exports semantic fields from `recognition_profile_snapshot_json`; CSV `notes` carries `supplier_import` metadata for backend revalidation. Full backend re-extraction against historical profile version **not yet wired**. |
| ITEM_SEMANTIC_EXTRACTION | **PASS** | Export maps label_id / sku / quantity from snapshot; raw segmented string blocked as SKU. |
| POSITION_SEMANTIC_EXTRACTION | **PASS** | Export emits `LOCAL_POSITION_LABEL` with position hierarchy; no product row. |
| RAW_PAYLOAD_NOT_SKU | **PASS** | `isLikelyRawSegmentedPayload` guard in export + scan persist; golden tests. |
| NO_ZERO_SENTINEL | **PASS** | Backend `_quantity_for` returns `None` (not 0); summary `final_quantity` null-safe. |
| POSITION_ONLY_PERSISTENCE | **PASS** | `LOCAL_POSITION_LABEL` skipped by materializer; no ProductRecord for position markers. |
| HISTORICAL_PROFILE_REVALIDATION | **FAIL** | Follow-up: parse `notes.supplier_import` and run `StructuredPayloadExtractor` against exact profile_id/version on import. |
| DINAMIC_REGRESSION | **PASS** | No changes to DINAMIC/TXT ingestion paths; existing materializer tests pass. |
| TESTS | **PASS** | Mobile: typecheck, test:core (327), test:services (273). Backend: `test_local_csv_position_materializer.py` (11). |

## Fixes applied

1. **Mobile `supplierExportSemantics.ts`** — snapshot → semantic ITEM/POSITION fields; raw segmented detection; `supplier_import` notes JSON.
2. **Mobile `buildLocalCsvExport.ts`** — export from snapshot; block raw fallback; POSITION-only rows; supplier position columns; import notes.
3. **Mobile `localCodeScanStrategy.ts`** — do not persist legacy raw segmented string as `internal_code` when supplier item valid.
4. **Backend `local_csv_position_materializer.py`** — quantity null handling; plain-text supplier position evidence; business position in summary; review only when product line missing qty.

## First divergence

See `audit/supplier-offline-import-first-divergence.md`. First broken stage was mobile export fallback + backend quantity sentinel.

## Follow-up recommendations

1. Backend import enricher: read `notes.supplier_import`, load profile by id+version, revalidate raw_payload (fail closed if profile missing).
2. Issued-label path: when supplier ITEM has label_id but registry unresolved, consider `requires_review` only when CSV `requires_review=true` and validation metadata present.
3. Device E2E: re-import golden ZIP for `pruebas b` and verify UI rows.

## Validation commands

```bash
cd mobile && npm run typecheck && npm run test:core && npm run test:services
cd backend && .venv/bin/pytest tests/unit/test_local_csv_position_materializer.py -q --no-cov
```

Results (2026-09-01): all commands PASS.
