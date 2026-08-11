# Implementation corrections validation — Phase 3 state reconciliation

**Date:** 2026-08-11

## Scope

Mandatory corrections after Phase 3 code review (verify-after-write, typed outcomes,
mandatory CAS, SQL race vs aisle worker, bounded retry). Does **not** reimplement
Phases 0–2.

## Fixes

1. `InventoryStatusReconciler.repair` uses optimistic CAS + verify-after-write with
   `MAX_RECONCILE_ATTEMPTS = 3` (no infinite loop; `RETRY_EXHAUSTED` leaves detectable drift).
2. Typed `InventoryStatusRepairOutcome` / `InventoryStatusRepairResult` (no `None` overload).
3. `reconcile() -> bool` = `True` only when outcome is `REPAIRED`.
4. `compare_and_set_status` on `InventoryRepository`; reconciler always calls it (no `getattr`).
5. Removed productive mutate+save fallback from reconciler; SQL CAS remains
   `UPDATE ... WHERE id = ? AND status = ?`.
6. `completed_at` set on enter COMPLETED / cleared on leave; never finish repair with
   COMPLETED when aisles no longer imply completed (verify-after-write).
7. SQL integration: reconciler vs aisle → PROCESSING / FAILED (Events, no sleep sync);
   concurrent repair asserts exactly one `REPAIRED`; fresh connection authority;
   detect-only zero writes; backfill repair then idempotent.
8. Unit reason matrix for all reason codes + retry exhaustion test double.

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

```text
exit code: 0
All checks passed!
```

## Mypy

```text
exit code: 0
Success: no issues found in 6 source files
```

## Evidence pack (gitignored dumps)

Regenerated from the working tree after these corrections (not reused from Phases 0–2):

- `implementation-corrections-status.txt`
- `implementation-corrections-diffstat.txt`
- `implementation-corrections-diff.txt`
- `review/implementation-corrections-*.txt`
- `review/phase3-state-reconciliation-corrections-*.txt`

## Status

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
