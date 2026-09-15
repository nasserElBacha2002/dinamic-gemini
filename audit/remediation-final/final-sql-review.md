# Final SQL review

## Bandit B608 priority triage

| Area | Classification |
|------|----------------|
| `sqlserver_business_data_cleanup.py` | SAFE_IDENTIFIER_ALLOWLIST — closed frozenset of `(schema,table)`; values not concatenated from request |
| `sql_local_csv_import_repository.py` | FALSE_POSITIVE_STATIC_SQL / PARAMETERIZED_SAFE — column constants + `?` binds; TOP capped int |
| Outbox / supplier profile / write policy / UoW / aisle repos / local CSV writer | PARAMETERIZED_SAFE or FALSE_POSITIVE_STATIC_SQL |
| **REQUIRES_FIX** | **None** in priority set |

## Soft-delete atomicity (Stage 2)

- Abstract `soft_delete_many_for_scope` (no non-transactional ABC default)
- SQL: UPDLOCK + OUTPUT inside transaction/UoW
- Tests: induced failure rollback, mixed scope, concurrent claim patterns

## Migrations

No new migration in this final phase. Soft-delete / tenant filters rely on existing schema.

## Residual SQL risks

- Broader Bandit B608 set outside priority files not exhaustively re-scanned line-by-line
- Concurrent position-merge flake under load
- Legacy `jobs` vs `inventory_jobs` dual paths remain for compatibility
