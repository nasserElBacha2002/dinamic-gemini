# SQL integration validation (Stage 2)

## Environment

- Local SQL Server via `tests/support/sql_integration.py` / resolved test connection string.
- Module: `backend/tests/integration/test_sql_tenant_isolation_stage2.py`.

## Command

```bash
cd backend
.venv/bin/python -m pytest -q tests/integration \
  -k "tenant or authorization or client or inventory or export" \
  --override-ini='addopts='
```

## Result

- **31 passed**, 60 deselected (2026-09-15).
- Covered: two synthetic clients A/B; company principals scoped on list/get clients and inventories; cross-tenant get → `ClientNotFoundError` / `InventoryNotFoundError`; platform sees both; `list_for_client` SQL path.

## Not covered in this SQL module (residual)

- Concurrent request races.
- Full HTTP export streaming against SQL fixtures.
- Bulk soft-delete transactional rollback at DB isolation level (use-case atomicity verified in unit/memory tests).
- Historical NULL `client_id` inventory cleanup (fail-closed documented separately).
