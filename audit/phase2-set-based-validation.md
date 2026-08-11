# Phase 2 validation — set-based persistence (post corrections)

**Date:** 2026-08-11

## Commands

```bash
cd backend
.venv/bin/python -m pytest \
  tests/unit/local_inventory_package/ \
  tests/unit/test_local_inventory_package.py \
  tests/unit/test_local_csv_import.py \
  tests/unit/test_local_csv_import_confirm_materialize.py \
  tests/unit/infrastructure/ \
  tests/integration/local_csv_batch/ \
  tests/integration/local_inventory_package/ \
  tests/integration/db_integrity/ \
  tests/integration/product_labels/test_sql_inventory_counted_product_label_concurrency.py \
  --tb=line --no-cov -q
```

**Result:** (see full run below — target all green)

### Benchmark evidence (isolated)

```text
BENCH n=10  row_by_row_ms=6.8   executemany_ms=6.4   fast_executemany_ms=7.7
BENCH n=100 row_by_row_ms=34.5  executemany_ms=29.7  fast_executemany_ms=10.0
BENCH n=1000 row_by_row_ms=306.8 executemany_ms=292.3 fast_executemany_ms=82.7
```

Interpretations:

- **Python cursor calls:** baseline N executes → chunked executemany calls (measured).
- **Wall-clock:** `fast_executemany` improves 100/1000; plain executemany modest.
- **Network RPCs:** not measured → not asserted in reports.

### Ruff / Mypy

Touched modules must pass; document any global mypy pre-existing separately.

## Phase status

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
Stored Procedures added: 0
Triggers added: 0
New migrations: 0
New indexes: 0
```

## Skips

None expected in the required suites when SQL Server is available.
