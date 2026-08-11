# Implementation validation — Phase 0 + Phase 1

## Commands

```bash
cd backend
.venv/bin/python -m pytest \
  tests/unit/local_inventory_package/test_package_confirm_transaction_boundary.py \
  tests/unit/test_local_inventory_package.py \
  tests/unit/test_local_csv_import.py -q
# → 20 passed

.venv/bin/python -m pytest \
  tests/integration/db_integrity/test_critical_unique_indexes_catalog.py \
  tests/integration/product_labels/test_sql_inventory_counted_product_label_concurrency.py \
  tests/infrastructure/pipeline/test_worker_phase2_part2_corrections.py -q
# → 16 passed, 9 skipped (0094/0095 / some tables not on local DB)

.venv/bin/ruff check <changed files>
# → All checks passed

.venv/bin/mypy \
  src/infrastructure/repositories/sql_local_inventory_package_repository.py \
  src/infrastructure/repositories/sql_local_csv_import_repository.py \
  src/application/use_cases/inventories/manage_local_inventory_package.py \
  src/infrastructure/database/sql_transaction.py
# → exit 0
```

## Phase status

```text
PHASE_0: COMPLETE
PHASE_1: COMPLETE
SPs added: 0
Triggers added: 0
```

## Notes

- Local SQL catalog skips for 0094/0095 until those migrations are applied on the test database.
- No API contract changes.
- `schema.sql` drift vs migrations documented; migrations remain source of truth.
