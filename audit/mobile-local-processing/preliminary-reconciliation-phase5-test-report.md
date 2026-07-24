# Preliminary reconciliation — Phase 5 test report

## Unit (backend)

```bash
./venv/bin/pytest backend/tests/application/services/test_preliminary_detection_compare.py \
  backend/tests/application/use_cases/test_reconcile_preliminary_detections.py \
  backend/tests/database/test_migration_0063_preliminary_reconciliations.py \
  -q --no-cov
```

**Result:** 19 passed.

Coverage includes: match variants, mismatch, local/remote only, both unresolved, ambiguous, leading zeros, GLOBAL_BATCH not comparable, idempotency, disabled flag, migration structure.

## API

`backend/tests/api/test_preliminary_reconciliations_routes.py` written.

**Not executed:** local `venv` missing `jwt` (`ModuleNotFoundError` on API app import).

## SQL Server

Live ODBC / concurrent unique tests: **not run**.

## Mobile

```bash
cd mobile && npm run typecheck   # PASS
cd mobile && npm run lint        # PASS
cd mobile && npm run test:services -- --testPathPattern='preliminaryReconciliationPhase5|localCodeScanStrategy'
# PASS 12 tests
cd mobile && npm run test:core -- --testPathPattern=featureFlags
# PASS 11 tests
```

## E2E / device

Full flow (scan → sync → process → reconcile → metrics) on device: **not run**.

## Ground-truth metrics

Manual labeled dataset vs human GT: **not produced** (documented limitation).
