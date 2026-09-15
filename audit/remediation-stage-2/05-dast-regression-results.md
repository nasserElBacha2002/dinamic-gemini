# DAST regression results (Stage 2)

## Status: **NOT_RUN** (LOCAL_ISOLATED_ONLY unavailable in this session)

Required environment: `LOCAL_ISOLATED_ONLY` — **not** DEV/production.

## Planned minimum matrix (for follow-up)

| Principal | Target | Expected |
|-----------|--------|----------|
| company_admin A | clients/inventories/exports A | 200 |
| company_admin A | clients/inventories/exports B | 403 or 404 |
| company_admin B | A resources | 403 or 404 |
| platform_admin | A and B | 200 |
| no token / invalid | any | 401 |

Routes: clients list/get/update; inventories list/get/update/metrics; six priority exports; one parent/child cross; bulk-soft-delete on disposable fixtures only.

## Lab substitute already executed

- HTTP unit matrix: `tests/api/test_tenant_isolation_stage2_http.py` (company A scoped; platform global; 401 when auth denied).
- Application matrix: `tests/application/use_cases/test_tenant_isolation_stage2.py`.
- SQL: `tests/integration/test_sql_tenant_isolation_stage2.py`.

These **do not** replace formal DAST A/B against a running LOCAL_ISOLATED stack. Stage status therefore cannot be `IMPLEMENTED_AND_VERIFIED`.
