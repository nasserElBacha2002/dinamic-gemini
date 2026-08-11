# Phase 3 validation — state reconciliation

**Date:** 2026-08-11

## Commands

```bash
cd backend
.venv/bin/python -m pytest \
  tests/domain/test_derive_inventory_status.py \
  tests/unit/inventory_status/ \
  tests/application/use_cases/test_inventory_status_lifecycle_and_backfill.py \
  tests/integration/inventory_status/ \
  tests/integration/local_inventory_package/ \
  tests/integration/local_csv_batch/ \
  tests/unit/local_inventory_package/ \
  tests/unit/test_local_csv_import_confirm_materialize.py \
  --tb=line --no-cov -q
```

**Result:** `50 passed`

### Ruff / Mypy (touched modules)

**Result:** pass

## Phase status

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
PHASE_3: COMPLETE
Stored Procedures added: 0
Triggers added: 0
Reconciliation jobs added: 0
Drift detectors added: 1
```

## Skips

None in the suite above when SQL Server is available.
