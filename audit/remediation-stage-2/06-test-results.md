# Test results (Stage 2)

## Focused authorization

```bash
.venv/bin/python -m pytest -q tests/api tests/application \
  -k "tenant or client_scope or authorization or inventory_access or export" \
  --override-ini='addopts='
```

- **98 passed**, 1876 deselected (after code_scans export stub fix).

## SQL integration

```bash
.venv/bin/python -m pytest -q tests/integration \
  -k "tenant or authorization or client or inventory or export" \
  --override-ini='addopts='
```

- **31 passed**, 60 deselected.

## Lint / types

```bash
.venv/bin/ruff check src/api/routes/v3 src/application src/domain src/infrastructure \
  tests/api tests/application tests/integration
# All checks passed

.venv/bin/mypy src/api/routes/v3 src/application src/domain src/infrastructure
# Success: no issues found in 894 source files
```

## Full pytest — first complete run (authoritative)

```bash
.venv/bin/python -m pytest -q --override-ini='addopts='
```

- **First complete run:** `2 failed, 5298 passed, 4 skipped` (~91s).
- Failures: `tests/api/test_error_mapping.py::test_get_inventory_not_found_returns_structured_json` and `::test_structured_api_error_logs_stable_code_at_info` — stubs called `execute(id)` but route now passes `(id, principal)`.
- Stubs updated to accept principal; those two tests then **passed** in isolation.
- **Second complete run (after stub fix):** `5300 passed, 4 skipped` (~90s), exit 0.
- Per Stage 2 rules, the first incomplete-green gate plus missing DAST still block `IMPLEMENTED_AND_VERIFIED`.

## New / updated Stage 2 tests

| File | Role |
|------|------|
| `tests/application/use_cases/test_tenant_isolation_stage2.py` | Use-case matrix |
| `tests/api/test_tenant_isolation_stage2_http.py` | HTTP matrix |
| `tests/integration/test_sql_tenant_isolation_stage2.py` | SQL A/B |
| Call-site updates across inventory/client use-case tests | principal required |
| `tests/api/test_code_scans_routes.py` | inventory repo stub for export Depends |
| `tests/api/test_error_mapping.py` | principal arity on get-inventory stubs |
