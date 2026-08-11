# Phase 3 validation — state reconciliation (post-corrections)

**Date:** 2026-08-11

## Corrections covered

- Verify-after-write + bounded retry (`MAX_RECONCILE_ATTEMPTS = 3`)
- Typed `InventoryStatusRepairOutcome` / `InventoryStatusRepairResult`
- `reconcile() -> bool` wrapper (`True` only on effective repair)
- `compare_and_set_status` on `InventoryRepository` (no `getattr`, no mutate+save fallback in reconciler)
- SQL races: reconciler vs aisle PROCESSING / FAILED; concurrent repair exact winner
- Detect-only + repair backfill SQL; reason matrix; `completed_at` enter/leave COMPLETED
- Thread `join` + `assert not t.is_alive()`; fresh SQL connection for final asserts

## Pytest

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

```text
exit code: 0
passed: 65
failed: 0
skipped: 0
```

## Ruff

```bash
.venv/bin/ruff check \
  src/application/services/inventory_status_reconciler.py \
  src/application/use_cases/inventories/backfill_inventory_statuses.py \
  src/backfill_inventory_status.py \
  src/domain/inventory \
  src/infrastructure/repositories/memory_inventory_repository.py \
  src/infrastructure/repositories/sql_inventory_repository.py \
  tests/domain/test_derive_inventory_status.py \
  tests/unit/inventory_status \
  tests/integration/inventory_status
```

```text
exit code: 0
All checks passed!
```

## Mypy

```bash
.venv/bin/mypy \
  src/application/services/inventory_status_reconciler.py \
  src/application/use_cases/inventories/backfill_inventory_statuses.py \
  src/backfill_inventory_status.py \
  src/domain/inventory/derive_status_from_aisles.py \
  src/infrastructure/repositories/memory_inventory_repository.py \
  src/infrastructure/repositories/sql_inventory_repository.py
```

```text
exit code: 0
Success: no issues found in 6 source files
```

## Definition of Done checklist

```text
reconciler vs reconciler ✅
reconciler vs aisle PROCESSING ✅
reconciler vs aisle FAILED ✅
CAS contract explicit ✅
no getattr fallback ✅
bounded retry ✅
thread termination ✅
completed_at consistent ✅
detect-only SQL zero writes ✅
reason matrix ✅
post-commit recovery ✅
pytest ✅
ruff ✅
mypy ✅
```

## Phase status

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
PHASE_2: COMPLETE
PHASE_3: COMPLETE

Stored Procedures added: 0
Triggers added: 0
New migrations: 0
Reconciliation jobs added: 0
Drift detectors added: 1
```

## Skips

None in the suite above when SQL Server is available.
