# DB integrity — final validation (Phase 6)

**Date:** 2026-08-11
**Git base (HEAD at validation):** `99be199960c5de080ec0d633e3f64dd25dffbaa8`
**Working tree:** Phase 6 uncommitted changes on top of HEAD (see `review/phase6-final-*`)

## Catalog / migration

| Check | Result |
| ----- | ------ |
| Migration HEAD (repo + applied) | `0095` |
| Pending migrations (integration DB) | `0` |
| Application Stored Procedures | `0` |
| Application Triggers (live `sys.triggers`) | `0` |
| Phase 6 new migrations | `0` |
| `UQ_icpl_inventory_label` | absent (0095) |
| `UQ_icpl_aisle_label` | present |
| 0094 legacy secondary uniques | absent |
| Critical uniques 0044/0056/0074/0084/0094/0095 | present as expected |
| `completed` ↔ `completed_at` drift rows | `0` / `0` |
| `completed_at` CHECK | **NO_ACTION** (follow-up closed) |

## Critical constraint spot-checks (SQL Server)

```text
UQ_source_assets_aisle_upload_batch_client=1
UQ_eiar_idempotency_key=1
UQ_manual_position_override_active=1
UQ_manual_position_override_idempotency=1
UX_local_csv_productive_label=1
UX_local_csv_import_rows_imported_label=1
UQ_icpl_aisle_label=1
UQ_icpl_inventory_label=0
triggers=0
app_procedures=0
```

## Pytest

### SQL integrity suite (§32)

```bash
cd backend
.venv/bin/python -m pytest \
  tests/integration/db_integrity/ \
  tests/integration/inventory_status/ \
  tests/integration/local_inventory_package/ \
  tests/integration/local_csv_batch/ \
  tests/integration/product_labels/test_sql_inventory_counted_product_label_concurrency.py \
  --tb=line --no-cov -q
```

```text
47 passed, 0 failed, 0 skipped
```

### Targeted regression (§36 + domain entities)

```bash
.venv/bin/python -m pytest \
  tests/domain/test_derive_inventory_status.py \
  tests/domain/v3/test_entities.py \
  tests/unit/inventory_status/ \
  tests/application/ports/test_ports_contract.py \
  tests/application/use_cases/test_inventory_status_lifecycle_and_backfill.py \
  tests/integration/inventory_status/ \
  tests/integration/local_inventory_package/ \
  tests/integration/local_csv_batch/ \
  tests/unit/local_inventory_package/ \
  tests/unit/test_local_csv_import_confirm_materialize.py \
  --tb=line --no-cov -q
```

```text
81 passed, 0 failed
```

### Stub CAS hygiene (Phase 3 residual)

```bash
.venv/bin/python -m pytest \
  tests/application/services/test_authoritative_aisle_finalization_phase6.py \
  tests/application/use_cases/test_confirm_position.py \
  tests/application/use_cases/test_delete_position.py \
  tests/application/use_cases/test_mark_position_image_mismatch.py \
  tests/application/use_cases/test_mark_position_unknown.py \
  tests/application/use_cases/test_update_product_quantity.py \
  tests/application/use_cases/test_update_product_sku.py \
  --tb=line --no-cov -q
```

```text
30 passed
```

### Full backend suite (§37)

```bash
.venv/bin/python -m pytest --tb=line --no-cov -q
```

```text
4448 passed, 6 skipped, 0 failed
```

Skipped: environmental / optional (not critical integrity skips). Classification: not regressions from Phases 0–6.

## Lint / types / git

| Check | Command | Result |
| ----- | ------- | ------ |
| Ruff | `.venv/bin/ruff check src tests` | **PASS** |
| Mypy | `.venv/bin/mypy src` | **PASS** (1123 files) |
| `git diff --check` | after trailing-whitespace strip on audit markdown | **PASS** |

## Phase rollup

| Phase | Status |
| ----- | ------ |
| 0 | COMPLETE |
| 1 | COMPLETE |
| 2 | COMPLETE |
| 3 | COMPLETE |
| 4 | NO_ACTION_REQUIRED |
| 5 | NO_ACTION_REQUIRED |
| 6 | COMPLETE |

```text
Migration HEAD: 0095
Pending migrations: 0
New migrations Phase 6: 0

Application Stored Procedures: 0
Application Triggers: 0

Critical SQL integration tests:
passed: 47
failed: 0
skipped: 0

Ruff: PASS
Mypy: PASS
git diff --check: PASS
```

## Security

```text
NO_NEW_SECURITY_SURFACE
```

## Definition of Done checklist

- [x] Phase 0–5 status reconciled with code
- [x] Migration HEAD verified
- [x] Pending migrations = 0
- [x] Critical constraints verified
- [x] Transaction boundaries verified (docs + package tests)
- [x] CAS contract final (abstract + stub hygiene)
- [x] Reconciler final
- [x] No trigger/SP accidental
- [x] completed_at follow-up resolved (NO_ACTION)
- [x] Dead code / temporary helpers reviewed
- [x] Repository hygiene clean
- [x] SQL integration regressions pass
- [x] Concurrency tests pass
- [x] Ruff pass
- [x] Mypy relevant pass
- [x] git diff --check pass
- [x] Canonical architecture document generated
- [x] Final validation document generated
