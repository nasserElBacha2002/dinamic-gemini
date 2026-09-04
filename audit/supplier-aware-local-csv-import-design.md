# Supplier-aware legacy CSV import — design

**Date:** 2026-09-01  
**Scope:** Legacy `DINAMIC_LOCAL_AISLE_EXPORT` / `results.csv` import only (no Phase 5 `.dinamic`).

## Problem

Supplier ITEM rows export `label_id=LPNA000184` in CSV column `label_id`. Legacy parser applied Dinamic D1 Crockford rules before any supplier profile lookup → `label_id:invalid_format` → `PACKAGE_NO_PRODUCTIVE_ROWS`.

## Discriminator

Rows are classified as **Supplier** only when `notes` JSON contains valid `supplier_import` metadata (mobile contract):

```json
{
  "supplier_import": {
    "client_supplier_id": "<uuid>",
    "label_kind": "ITEM" | "POSITION",
    "profile_id": "<uuid>",
    "profile_version": 10,
    "raw_payload": "LPNA000184|SKU773421|24"
  }
}
```

No inference from prefix, pipe count, supplier name, or `source` alone.

## Pipeline (preview + confirm)

```
parse_local_csv
  → parse supplier_import from notes (typed)
  → D1 label_id ONLY when supplier_import absent
  → PreviewLocalCsvImport._build_and_persist_preview
      → SupplierLocalCsvRowRevalidator (per row)
          → ExactExtractionProfileVersionService (historical, kind-scoped)
          → StructuredPayloadExtractor + LabelValidationService
          → semantic compare CSV vs backend
          → authoritative fields persisted on LocalCsvImportRow
  → assert_package_csv_rows_ready (unchanged)
ConfirmLocalCsvImport
  → uses staged rows (preview/confirm parity)
```

## Components

| Module | Role |
|--------|------|
| `local_csv_supplier_import_metadata.py` | Typed `supplier_import` parser |
| `supplier_local_csv_row_revalidator.py` | Profile load + extract + validate + mismatch |
| `exact_extraction_profile_version.py` | Reused historical profile attestation |
| `local_csv_parser.py` | Structural CSV; supplier vs D1 branch on `label_id` |
| `label_validation_service.py` | CSV recognition may omit symbology (transport) |

## Error codes

| Code | When |
|------|------|
| `label_id:invalid_format` | Dinamic D1 rows only |
| `supplier_import:*` | Malformed metadata |
| `SUPPLIER_PROFILE_VERSION_NOT_AVAILABLE` | Pinned version missing |
| `supplier_profile:scope_mismatch` | Wrong supplier/kind/tenant |
| `supplier_semantic_mismatch:*` | CSV tamper vs backend |
| `LABEL_*` | Supplier validation (prefix, segments, etc.) |

## Out of scope

- Phase 5 `DINAMIC_OFFLINE_AISLE` import
- Mobile export changes (follow-up: ensure ITEM rows include `raw_payload` in notes when `product_results_json` is populated)

## Phase 5 reuse

Same `SupplierLocalCsvRowRevalidator` + metadata shape can validate capture `recognitions.*` later without duplicating split/regex logic.
