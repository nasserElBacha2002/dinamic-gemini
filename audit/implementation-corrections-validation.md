# Implementation corrections validation — supplier-aware legacy CSV import

**Date:** 2026-09-01  
**Status:** `CORRECTIONS_VALIDATED`

## Acceptance matrix

| Check | Status |
|-------|--------|
| SUPPLIER_CSV_DISCRIMINATION | PASS |
| D1_REGRESSION | PASS |
| HISTORICAL_PROFILE_LOOKUP | PASS |
| STRUCTURED_EXTRACTION | PASS |
| SUPPLIER_VALIDATION | PASS |
| SEMANTIC_MISMATCH_DETECTION | PASS |
| GOLDEN_ITEM | PASS |
| GOLDEN_POSITION | PASS |
| MIXED_PACKAGE | PASS |
| PREVIEW_CONFIRM_PARITY | PASS |
| TESTS | PASS |

## Summary

- Supplier rows identified via `notes.supplier_import` only.
- D1 `label_id:invalid_format` no longer applied to Supplier ITEM (`LPNA000184`).
- Historical profile v10 loaded via `ExactExtractionProfileVersionService` (no ACTIVE fallback).
- `StructuredPayloadExtractor` + `LabelValidationService` reused; CSV transport omits symbology (allowed for `RecognitionSource.CSV`).
- Backend authoritative `internal_code` / `quantity` / `label_id` persisted at preview; confirm uses staged rows.

## Tests run

```bash
../.venv/bin/pytest tests/unit/test_supplier_local_csv_import.py -q --no-cov
# 18 passed

../.venv/bin/pytest tests/unit/test_supplier_local_csv_import.py \
  tests/unit/test_local_csv_import.py \
  tests/unit/test_label_validation_service.py -q --no-cov
# 38 passed

../.venv/bin/pytest tests/unit/test_local_inventory_package.py \
  tests/unit/test_structured_payload_extractor_pr1.py \
  tests/unit/test_exact_extraction_profile_version.py -q --no-cov
# 34 passed

../.venv/bin/ruff check <changed files>
# pass (after F841 fix)
```

## Follow-up

- **Mobile:** `buildLocalCsvRows` may omit `raw_payload` in `supplier_import` for resolved ITEM rows (when `internal_code` is SKU, not raw). Backend fails closed with `supplier_import:missing_raw_payload`. Consider exporting scan evidence raw in notes.

## DEVICE_E2E

UNVERIFIED — requires device re-import of pruebas b golden ZIP.
