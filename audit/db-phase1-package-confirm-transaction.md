# Fase 1 — Package Confirm transactional boundary (post-corrections)

**Resultado:** `COMPLETE`  
**Fecha:** 2026-08-11  
**SPs added:** 0  
**Triggers added:** 0  
**API contract changes:** none

## After (implemented)

```text
Optimistic status gate (CONFIRMED | PREVIEWED | else INVALID, no side effects)
→ assert physical staging files exist (no storage/SourceAsset yet)
→ PLAN TX: UPDLOCK package → select rows_to_import → ROLLBACK (release locks)
→ EXTERNAL: stage SourceAssets ONLY for rows_to_import
→ APPLY TX: UPDLOCK package → revalidate → productive writes + CSV CONFIRMED + package CONFIRMED
→ COMMIT once
→ POST-COMMIT: position materialize + aisle finalize (retryable on idempotent re-confirm)
```

CSV-only:

```text
BEGIN TX → writer.apply_import(cursor) → CSV CONFIRMED → COMMIT
→ post-commit position materialize + aisle mark
```

## SQL Server evidence

`tests/integration/local_inventory_package/test_sql_package_confirm_transaction.py`:

| Case | Result |
| ---- | ------ |
| A Happy path + fresh connection read | pass |
| B Productive failure → both PREVIEWED | pass |
| C Fail after CSV before package UPDATE → rollback both | pass |
| D Concurrent double confirm (2 connections) | pass |
| E Re-confirm no new productives | pass |
| F Invalid status gate, 0 storage/productive | pass |
| G SKIP conflict → DUPLICATE, no extra productive | pass |
| H REJECT conflict → error, no leftovers | pass |

## Failure matrix (storage vs SQL)

| Failure point | DB | Storage/assets | Retry |
| ------------- | -- | -------------- | ----- |
| Invalid status (optimistic) | unchanged | none | n/a |
| REJECT in plan TX | unchanged | none | fix conflict |
| Staging failure | unchanged | partial recoverable | retry |
| Productive mid-apply | rollback PREVIEWED | may have staged assets | retry idempotent UQ |
| After CSV before package UPDATE | rollback both | staged assets may remain | retry |
| Post-commit materialize fail | CONFIRMED committed | ok | re-confirm idempotent + rematerialize |

## Transaction ownership

- Opens TX: `SqlLocalInventoryPackageRepository` (`begin_transaction`)
- Cursor: shared via `sql_repository_cursor(..., connection=txn.connection)`
- Commit: apply phase only
- Plan phase: explicit rollback / ACTIVE exit rollback
- `SqlServerTransaction.__exit__`: rollback if ACTIVE (unit-tested)
