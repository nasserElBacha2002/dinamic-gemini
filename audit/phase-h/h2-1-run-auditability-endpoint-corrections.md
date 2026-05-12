# H2.1 — Run auditability endpoint corrections

## 1. Executive summary

**Final status:** `READY_FOR_H3_WITH_GAPS`

Corrections from the H2 code review are implemented in tests and documentation. **HTTP tests were not executed on Python 3.10+ in this validation environment** (only `/usr/bin/python3` at **3.9.6** is available; no `python3.10` / `python3.11` / `python3.12` on `PATH`). The module still **skips** below 3.10; CI or a local 3.10+ interpreter must run the HTTP file to claim green HTTP coverage.

H3 can start for the internal debugging panel, provided **CI (or developers) run** `pytest tests/application/api/test_job_auditability_endpoint.py` on **Python 3.10+** at least once before release.

---

## 2. Corrections implemented

| Item | Outcome |
|------|---------|
| **Python 3.10+ HTTP test run** | **Not run here** — blocker documented (no 3.10+ binary in environment). Command to use when available is in §5. |
| **Legacy HTTP test** | Replaced with a **real legacy shape**: separate inventory (`client_id=None`) and aisle (`client_supplier_id=None`), job targeting that aisle; asserts `legacy_mode`, `client_id`, `client_supplier_id` all null; URL still uses inventory/aisle/job scope. |
| **Cross-scope 404** | Added `test_get_job_auditability_cross_scope_wrong_aisle_404`: job targets another aisle under the same inventory; request uses the primary aisle in the URL; expects **404** and `detail == HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C`. |
| **Test file location** | **Kept** `backend/tests/application/api/test_job_auditability_endpoint.py`. Most v3 route tests live under `tests/api/`, but `tests/api/conftest.py` imports `app` at module import time and fails on **Python 3.9** (`Settings | None` in auth config) *before* this file’s module-level `pytest.skip` runs. Placing the file under `tests/application/api` avoids that conftest and preserves a clean **targeted** `pytest …/test_job_auditability_endpoint.py` on 3.9 (skip) vs 3.10+ (run). |
| **FastAPI `response_model`** | **Intentionally omitted** — handler returns `dict[str, Any]` from `RunAuditabilityView.to_jsonable()` to avoid duplicating the H1 read model in OpenAPI; stable JSON for H3; a formal Pydantic schema can be added later if OpenAPI/codegen requires it. |

---

## 3. Files changed

| File | Change |
|------|--------|
| `backend/tests/application/api/test_job_auditability_endpoint.py` | Legacy test data fix; cross-scope 404 test; docstring for location/skip; duplicate `pytest` import removed; `HTTP_DETAIL_JOB_NOT_IN_AISLE_CATEGORY_C` assertion. |
| `audit/phase-h/h2-1-run-auditability-endpoint-corrections.md` | This report. |

No changes to `aisles.py`, `dependencies.py`, `run_auditability_service.py`, or route contract.

---

## 4. Endpoint contract confirmation

| Check | Status |
|-------|--------|
| **Path** | `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability` |
| **200** | Resolvable job in scope (unchanged). |
| **200 partial** | Missing hybrid / execution log / metadata still 200 with `metadata_sources` / `missing_metadata` (unchanged). |
| **404 unknown job** | Still covered. |
| **404 out of scope** | Cross-scope job vs URL aisle → 404 with fixed Phase 6 detail string (same as execution-log wiring tests). |
| **Protected prompt text** | Not exposed; contract unchanged. |

---

## 5. Tests and validation

**Environment:** macOS validation host, **Python 3.9.6** only.

### Commands run (actual)

```bash
cd backend
python3 -m ruff check tests/application/api/test_job_auditability_endpoint.py
python3 -m pytest tests/application/api/test_job_auditability_endpoint.py \
  tests/application/services/test_run_auditability_models.py \
  tests/application/services/test_run_auditability_service.py \
  tests/application/services/test_run_auditability_execution_log.py \
  tests/application/services/test_reference_usage_from_job_result.py -q
```

**Results:** `ruff` **passed**. `pytest`: **15 passed, 1 skipped** (HTTP module skipped on 3.9).

### Command not run (blocker: no interpreter)

```bash
cd backend
python3.10 -m pytest tests/application/api/test_job_auditability_endpoint.py -q
```

**Status:** **Not executed** — `python3.10` not available on `PATH` in this environment. **Do not treat HTTP tests as passed until this is run on 3.10+.**

### Lint paths (as requested; adjusted for final file location)

```bash
cd backend
python3 -m ruff check tests/application/api/test_job_auditability_endpoint.py \
  src/api/routes/v3/aisles.py src/api/dependencies.py \
  src/application/services/run_auditability_service.py \
  src/application/services/reference_usage_from_job_result.py
```

(No edits to those `src/` files in H2.1; check is clean.)

---

## 6. Remaining gaps

- HTTP file **not** executed on 3.10+ here; CI must cover it.
- No frontend panel, SQL audit persistence, metrics endpoint, or top-level `GET /api/v3/jobs/{job_id}/auditability`.
- `inventory_visual_references_used` still `null` (H1 gap).

---

## 7. Final recommendation for H3

**Proceed** with **H3 — frontend internal debugging panel**, wiring the same inventory/aisle/job path. Treat **Python 3.10+ pytest** for `test_job_auditability_endpoint.py` as a **merge gate** until the repo standardizes on 3.10+ for all `tests/api` collection on developer machines.
