# Supplier pruebas b — profile correction (final)

**ClientSupplier:** `c314c8c3-b6fd-490c-98dc-7b1ac40dca47`  
**Date:** 2026-09-01

## Summary

Corrected supplier recognition for `pruebas b` using the productive `create + activate + effective_source=SUPPLIER` flow.

**Critical code fix:** `supplier_extraction_profile_activation.py` called non-existent `sql_client.transaction()`; SQL Server uses `begin_transaction()`. This prevented wiring persistence on every SQL activation attempt.

## Profiles created

| Kind | ACTIVE id | version | wiring source |
|------|-----------|---------|---------------|
| ITEM | `99563751-dfb4-438e-a666-f0b539a5c6a5` | 10 | SUPPLIER |
| POSITION | `602caad9-ab2d-4e89-8f00-57951b83c05f` | 3 | SUPPLIER |

## Configuration

- ITEM: SEGMENTED `|`, 3 segments, LPNA prefix, mappings label_id/sku/quantity
- POSITION: SEGMENTED `|`, 4 segments, A04 prefix, mappings position_id/pallet/side/level

## Verification chain

| Step | Result |
|------|--------|
| DB wiring (2 rows SUPPLIER) | PASS |
| LabelProfileResolver | PASS (both SUPPLIER / CLIENT_SUPPLIER) |
| Payload dry-run ITEM | PASS (VALID, qty=24) |
| Payload dry-run POSITION | PASS (VALID, A04-R-02…) |
| New job snapshot | PASS job `68aae986-4429-40d5-9da1-4646a8f7e72f` |
| CODE_SCAN asset ad40b787 | PASS `RESOLVED_INTERNAL` (no MISSING_QUANTITY) |
| CODE_SCAN events | SUPPLIER profile_version 10/3 |
| DB product/position materialization | WARN `PROCESSING_INCOMPLETE_RESULT` |

## New job

- **Job:** `68aae986-4429-40d5-9da1-4646a8f7e72f`
- Asset `ad40b787`: decode OK → SUPPLIER profiles → `code_scan.asset_finalized status=RESOLVED_INTERNAL`
- Asset `f02bf599`: `NO_CODE_SYMBOL_FOUND` (decoder; separate from wiring)

## Residual gap

POSITION-only `RESOLVED_INTERNAL` is recognized at CODE_SCAN strategy level but `code_scan_asset_processor` maps persist skip `MISSING_CODE_OR_QUANTITY` → `PENDING_MANUAL_REVIEW` / `PROCESSING_INCOMPLETE_RESULT`. Recognition chain is fixed; position materialization counters need a follow-up (out of scope: job executor).

## Code changes

1. `pruebas_b_segmented_configurations.py` — shared productive configs
2. `supplier_extraction_profile_activation.py` — `begin_transaction()` fix
3. `test_pruebas_b_productive_segmented_payloads` — regression test
4. `scripts/apply_pruebas_b_supplier_correction.py` — operational script
