# H2 — Backend run auditability endpoint

## 1. Executive summary

**Final status:** `READY_FOR_H3_WITH_GAPS`

H2 exposes the H1 `RunAuditabilityView` as a **read-only** JSON endpoint, reusing `RunAuditabilityService` and the same inventory-scoped job resolution pattern as hybrid-report and execution-log routes. No pipeline changes, no migrations, no new persistence, no metrics endpoints, and no frontend.

**Gaps carried forward:** no internal UI yet; no additive SQL audit columns; `inventory_visual_references_used` remains `null` until a reliable v3 signal exists; HTTP contract tests are **skipped below Python 3.10** (module-level `pytest.skip`) because importing the app pulls domain types that use `dataclass(kw_only=True)`.

---

## 2. What was implemented

| Path | Responsibility |
|------|----------------|
| `backend/src/api/routes/v3/aisles.py` | `GET …/jobs/{job_id}/auditability` — thin handler: resolve job for inventory/aisle, `audit_svc.build(job_id)`, 404 if no view, else `view.to_jsonable()` |
| `backend/src/api/dependencies.py` | `get_run_auditability_service()` — wires `RunAuditabilityService` with repos, `DefaultStoredArtifactReader`, `DefaultRunAuditExecutionLogLoader` |
| `backend/src/application/services/reference_usage_from_job_result.py` | `VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY` (aligned with pipeline run metadata comment); avoids application importing `src.pipeline.run_metadata` |
| `backend/src/application/services/run_auditability_service.py` | H1 hardening: `missing_metadata` includes `aisle_row` / `inventory_row` when joins are absent for aisle targets |
| `backend/tests/application/services/test_run_auditability_models.py` | `RunAuditabilityView.to_jsonable()` contract (ISO datetimes, nested structures, list copy semantics) |
| `backend/tests/application/services/test_run_auditability_service.py` | Non-aisle target; missing aisle; missing inventory |
| `backend/tests/application/api/test_job_auditability_endpoint.py` | HTTP tests: happy path, missing hybrid + execution log, 404, legacy, failed job (Python 3.10+ only; skipped below) |
| `backend/tests/conftest.py` | Removed ineffective `pytest_ignore_collect` for this module (import still ran on 3.9) |

---

## 3. Endpoint contract

| Item | Detail |
|------|--------|
| **Method** | `GET` |
| **Path** | `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/auditability` |
| **Rationale** | v3 does not expose a top-level `/api/v3/jobs/...` router; job reads for artifacts are inventory- and aisle-scoped. Same pattern as `GET …/hybrid-report`. |
| **Response** | JSON object from `RunAuditabilityView.to_jsonable()` (H1 contract). |
| **404** | Unknown `job_id`, or job not resolvable for the given inventory/aisle (same use case as sibling routes); project `HTTP_DETAIL_JOB_NOT_FOUND` style. |
| **Partial metadata** | Always **200** when the job resolves: missing `hybrid_report` / `execution_log` / joins do not raise; `metadata_sources` and `missing_metadata` describe gaps. |
| **Storage errors** | Not surfaced as raw client errors; artifact reads remain best-effort inside H1/H2 stack (no new exception mapping in the route beyond “no view → 404”). |

---

## 4. Dependency wiring

`get_run_auditability_service` in `backend/src/api/dependencies.py` constructs:

- `RunAuditabilityService(job_repo, aisle_repo, inventory_repo, stored_artifact_reader, execution_log_loader)`
- `stored_artifact_reader = DefaultStoredArtifactReader(job_repo, artifact_storage)`
- `execution_log_loader = DefaultRunAuditExecutionLogLoader(artifact_storage)`

Infrastructure types are constructed in the dependency factory (existing API pattern), not inside the application service.

---

## 5. Authorization / access behavior

Matches **existing** v3 aisle job routes: `get_current_admin` (and the same dependency graph as other inventory aisle job endpoints), plus `ResolveAisleJobForInventoryReadUseCase` via `_load_job_for_inventory_job_route` so the job must belong to the aisle under the inventory. H2 does **not** introduce RBAC or a new permission model.

---

## 6. Legacy and missing artifact behavior

- **Legacy jobs** (no `client_id` / `client_supplier_id` on the resolved view): **200**, `legacy_mode: true`, null-safe fields.
- **Missing hybrid report / execution log**: **200**, `metadata_sources.hybrid_report` / `execution_log` false, corresponding keys in `missing_metadata`.
- **Failed jobs** with empty `result_json`: **200**, `status` reflects failure, `missing_metadata` lists absent prompt/artifact fields as computed by the service.
- **Prompt text**: endpoint exposes hashes, versions, flags, and summaries per H1 — not full protected prompt bodies unless already implied elsewhere (unchanged from H1).

---

## 7. H1 observations addressed

| Observation | Status |
|-------------|--------|
| `to_jsonable()` unit test | Added in `test_run_auditability_models.py` |
| Non-aisle `target_type` service test | Added |
| Missing aisle / missing inventory join tests | Added; `missing_metadata` includes `aisle_row` / `inventory_row` where applicable |
| Remove application → `RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT` import | Done via `VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY` in `reference_usage_from_job_result.py` with alignment comment |

---

## 8. Tests and validation

Commands run (local environment **Python 3.9.6**):

```bash
cd backend
python3 -m pytest tests/application/services/test_run_auditability_models.py \
  tests/application/services/test_run_auditability_service.py \
  tests/application/services/test_run_auditability_execution_log.py \
  tests/application/services/test_reference_usage_from_job_result.py \
  tests/application/api/test_job_auditability_endpoint.py -q
```

**Result:** all targeted service tests **passed**; `test_job_auditability_endpoint.py` **skipped** (whole module) on Python 3.9 because of `dataclass(kw_only=True)` in the import graph.

```bash
cd backend
python3 -m ruff check tests/application/api/test_job_auditability_endpoint.py tests/conftest.py
```

**Result:** clean.

**Re-run HTTP tests on Python 3.10+** in CI or locally:

```bash
cd backend
python3.10 -m pytest tests/application/api/test_job_auditability_endpoint.py -q
```

---

## 9. Remaining gaps

- No frontend debugging panel (H3 candidate).
- No metrics-only endpoint or SQL rollups.
- No additive persistence for run-level audit columns.
- `inventory_visual_references_used` still `null` without a reliable artifact/result signal.
- Preferred bare `GET /api/v3/jobs/{job_id}/auditability` not added (would need new router + consistent access checks).

---

## 10. Final recommendation for H3

**Recommend:** `frontend internal debugging panel` (read-only) calling this endpoint from an admin or support context, plus **optional** polish: a job-scoped route only if product/security agrees it can reuse the same resolution rules without aisle/inventory path parameters.

**Not blocked** by API issues for an internal panel; contract is stable via `to_jsonable()`.
