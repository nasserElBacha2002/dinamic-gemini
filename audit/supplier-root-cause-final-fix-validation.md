# Validation — supplier root cause final fix

## Tests

| Command | Result |
|---------|--------|
| `pytest tests/unit/test_supplier_profile_runtime_wiring.py -q` | 13 passed |
| `pytest tests/unit/test_supplier_profile_runtime_wiring.py::test_pruebas_b_productive_segmented_payloads -q` | passed |

## Live verification (apply_pruebas_b_supplier_correction.py --full)

| Gate | Result |
|------|--------|
| Wiring DB | PASS |
| Resolver | PASS |
| Payload dry-run | PASS |
| Job snapshot SUPPLIER | PASS |
| CODE_SCAN RESOLVED_INTERNAL (POSITION payload) | PASS |
| No MISSING_QUANTITY | PASS |
| DB position/product materialization | WARN |

## Root cause addition

SQL atomic activation called `sql_client.transaction()` which does not exist on `SqlServerClient` (correct API: `begin_transaction()`). Wiring upsert never committed on SQL path even when UI sent `effective_source=SUPPLIER`.
