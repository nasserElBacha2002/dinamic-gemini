# Use Cases Phase 2 Move Report

## 1. Executive summary

**Status:** COMPLETED_WITH_WARNINGS — import/module validation passed; full pytest has 2 known failures unrelated to the move (not proven otherwise).

All **74** use case modules mapped in the audit were moved with `git mv` into **10** domain packages under `backend/src/application/use_cases/`. Import paths were updated across **114** Python files (backend source, tests, API routes, dependencies, pipeline, backfill scripts, runtime containers).

No business logic, class names, or function names were intentionally changed. **Ruff** auto-fixed **20** import-sort violations (`I001`) on `src/` during the move — import organization only, no logic edits.

**Import-related validation (post-move):** `mypy src` (CI scope) passed. `python -m compileall backend` completed with exit code 0 (see §5 for `.venv` caveat).

**Full-suite validation:** `pytest` did **not** pass — **2 failed**, 2454 passed, 29 skipped. Failures are documented as known non-import issues (`SUPPLIER_PROMPT_CONFIG_INVALID_MODEL`, local ODBC/memory fallback). Do not treat this suite as green until those tests pass in CI or are triaged separately.

**Review follow-up (report/tooling only):** pytest wording corrected; `__init__.py` description corrected; one-shot migration script removed from `scripts/`; validation table aligned with original DoD commands (§5).

---

## 2. Files moved

| Old path | New path |
|----------|----------|
| `use_cases/review_validation.py` | `use_cases/shared/review_validation.py` |
| `use_cases/benchmark_compare_support.py` | `use_cases/shared/benchmark_compare_support.py` |
| `use_cases/capture_session_group_assignment_guard.py` | `use_cases/shared/capture_session_group_assignment_guard.py` |
| `use_cases/create_inventory.py` | `use_cases/inventories/create_inventory.py` |
| `use_cases/get_inventory.py` | `use_cases/inventories/get_inventory.py` |
| `use_cases/list_inventories.py` | `use_cases/inventories/list_inventories.py` |
| `use_cases/list_inventory_list_items.py` | `use_cases/inventories/list_inventory_list_items.py` |
| `use_cases/get_inventory_metrics.py` | `use_cases/inventories/get_inventory_metrics.py` |
| `use_cases/backfill_inventory_statuses.py` | `use_cases/inventories/backfill_inventory_statuses.py` |
| `use_cases/export_inventory_results.py` | `use_cases/inventories/export_inventory_results.py` |
| `use_cases/export_inventory_business.py` | `use_cases/inventories/export_inventory_business.py` |
| `use_cases/create_aisle.py` | `use_cases/aisles/create_aisle.py` |
| `use_cases/list_aisles_by_inventory.py` | `use_cases/aisles/list_aisles_by_inventory.py` |
| `use_cases/list_aisles_with_status.py` | `use_cases/aisles/list_aisles_with_status.py` |
| `use_cases/get_aisle_processing_status.py` | `use_cases/aisles/get_aisle_processing_status.py` |
| `use_cases/start_aisle_processing.py` | `use_cases/aisles/start_aisle_processing.py` |
| `use_cases/cancel_aisle_job.py` | `use_cases/aisles/cancel_aisle_job.py` |
| `use_cases/retry_aisle_job.py` | `use_cases/aisles/retry_aisle_job.py` |
| `use_cases/list_aisle_jobs.py` | `use_cases/aisles/list_aisle_jobs.py` |
| `use_cases/promote_aisle_operational_job.py` | `use_cases/aisles/promote_aisle_operational_job.py` |
| `use_cases/resolve_aisle_job_for_inventory_read.py` | `use_cases/aisles/resolve_aisle_job_for_inventory_read.py` |
| `use_cases/run_aisle_merge.py` | `use_cases/aisles/run_aisle_merge.py` |
| `use_cases/get_aisle_merge_results.py` | `use_cases/aisles/get_aisle_merge_results.py` |
| `use_cases/upload_aisle_assets.py` | `use_cases/aisles/upload_aisle_assets.py` |
| `use_cases/list_aisle_assets.py` | `use_cases/aisles/list_aisle_assets.py` |
| `use_cases/delete_aisle_source_asset.py` | `use_cases/aisles/delete_aisle_source_asset.py` |
| `use_cases/backfill_legacy_aisles.py` | `use_cases/aisles/backfill_legacy_aisles.py` |
| `use_cases/list_aisle_positions.py` | `use_cases/positions/list_aisle_positions.py` |
| `use_cases/get_position_detail.py` | `use_cases/positions/get_position_detail.py` |
| `use_cases/get_position_code_scan_evidence.py` | `use_cases/positions/get_position_code_scan_evidence.py` |
| `use_cases/confirm_position.py` | `use_cases/positions/confirm_position.py` |
| `use_cases/delete_position.py` | `use_cases/positions/delete_position.py` |
| `use_cases/update_position_code.py` | `use_cases/positions/update_position_code.py` |
| `use_cases/update_product_quantity.py` | `use_cases/positions/update_product_quantity.py` |
| `use_cases/update_product_sku.py` | `use_cases/positions/update_product_sku.py` |
| `use_cases/mark_position_unknown.py` | `use_cases/positions/mark_position_unknown.py` |
| `use_cases/mark_position_image_mismatch.py` | `use_cases/positions/mark_position_image_mismatch.py` |
| `use_cases/list_review_queue.py` | `use_cases/positions/list_review_queue.py` |
| `use_cases/create_client.py` | `use_cases/clients/create_client.py` |
| `use_cases/get_client.py` | `use_cases/clients/get_client.py` |
| `use_cases/list_clients.py` | `use_cases/clients/list_clients.py` |
| `use_cases/create_client_supplier.py` | `use_cases/suppliers/create_client_supplier.py` |
| `use_cases/get_client_supplier.py` | `use_cases/suppliers/get_client_supplier.py` |
| `use_cases/list_client_suppliers.py` | `use_cases/suppliers/list_client_suppliers.py` |
| `use_cases/manage_supplier_prompt_configs.py` | `use_cases/suppliers/manage_supplier_prompt_configs.py` |
| `use_cases/manage_supplier_reference_images.py` | `use_cases/suppliers/manage_supplier_reference_images.py` |
| `use_cases/upload_supplier_reference_images.py` | `use_cases/suppliers/upload_supplier_reference_images.py` |
| `use_cases/backfill_legacy_client_supplier_defaults.py` | `use_cases/suppliers/backfill_legacy_client_supplier_defaults.py` |
| `use_cases/create_capture_session.py` | `use_cases/capture_sessions/create_capture_session.py` |
| `use_cases/close_capture_session.py` | `use_cases/capture_sessions/close_capture_session.py` |
| `use_cases/cancel_capture_session.py` | `use_cases/capture_sessions/cancel_capture_session.py` |
| `use_cases/list_capture_sessions.py` | `use_cases/capture_sessions/list_capture_sessions.py` |
| `use_cases/get_capture_session_detail.py` | `use_cases/capture_sessions/get_capture_session_detail.py` |
| `use_cases/upload_capture_session_staging_items.py` | `use_cases/capture_sessions/upload_capture_session_staging_items.py` |
| `use_cases/update_capture_session_clock_offset.py` | `use_cases/capture_sessions/update_capture_session_clock_offset.py` |
| `use_cases/compute_capture_session_assignment_preview.py` | `use_cases/capture_sessions/compute_capture_session_assignment_preview.py` |
| `use_cases/compute_capture_session_groups.py` | `use_cases/capture_sessions/compute_capture_session_groups.py` |
| `use_cases/get_capture_session_groups.py` | `use_cases/capture_sessions/get_capture_session_groups.py` |
| `use_cases/assign_capture_session_group_to_existing_aisle.py` | `use_cases/capture_sessions/assign_capture_session_group_to_existing_aisle.py` |
| `use_cases/create_aisle_and_assign_capture_session_group.py` | `use_cases/capture_sessions/create_aisle_and_assign_capture_session_group.py` |
| `use_cases/compute_materialized_capture_session_group_preview.py` | `use_cases/capture_sessions/compute_materialized_capture_session_group_preview.py` |
| `use_cases/materialize_capture_session.py` | `use_cases/capture_sessions/materialize_capture_session.py` |
| `use_cases/materialize_capture_session_group.py` | `use_cases/capture_sessions/materialize_capture_session_group.py` |
| `use_cases/run_aisle_code_scan.py` | `use_cases/code_scans/run_aisle_code_scan.py` |
| `use_cases/list_aisle_code_scans.py` | `use_cases/code_scans/list_aisle_code_scans.py` |
| `use_cases/summarize_aisle_code_scans.py` | `use_cases/code_scans/summarize_aisle_code_scans.py` |
| `use_cases/match_aisle_code_scan_detections.py` | `use_cases/code_scans/match_aisle_code_scan_detections.py` |
| `use_cases/get_aisle_code_scan_review_signals.py` | `use_cases/code_scans/get_aisle_code_scan_review_signals.py` |
| `use_cases/export_aisle_code_scans.py` | `use_cases/code_scans/export_aisle_code_scans.py` |
| `use_cases/compare_aisle_runs.py` | `use_cases/analytics/compare_aisle_runs.py` |
| `use_cases/compare_many_aisle_runs.py` | `use_cases/analytics/compare_many_aisle_runs.py` |
| `use_cases/export_aisle_benchmark.py` | `use_cases/analytics/export_aisle_benchmark.py` |
| `use_cases/persist_aisle_result.py` | `use_cases/pipeline/persist_aisle_result.py` |
| `use_cases/recompute_consolidated_counts.py` | `use_cases/pipeline/recompute_consolidated_counts.py` |

*Paths relative to `backend/src/application/`.*

**Package `__init__.py` files created:** `shared`, `inventories`, `aisles`, `positions`, `clients`, `suppliers`, `capture_sessions`, `code_scans`, `analytics`, `pipeline` — **empty package marker files** (0-byte `__init__.py` so Python treats each folder as a package; no docstrings).

---

## 3. Import surfaces updated

| Area | Updated? | Notes |
|------|----------|-------|
| `api/dependencies.py` | yes | All ~50 use case imports + lazy factory imports |
| v3 routes | yes | `aisles`, `capture_sessions`, `clients`, `inventories`, `positions`, `reviews`, `shared`, `assets`, `code_scans`, `analytics_api`, `review_queue` |
| tests | yes | 62+ modules under `backend/tests/` |
| pipeline/backfill/scripts | yes | `v3_job_executor.py`, `backfill_*.py`, `use_case_builders.py`, `prompt_config_builders.py`, `app_container.py`, services |
| `use_cases/__init__.py` | yes | Barrel now imports from `inventories.*` (still exports only Create/List inventory) |

---

## 4. Files intentionally left unmoved

| File | Reason |
|------|--------|
| `use_cases/__init__.py` | Package root barrel — updated in place |

No unmapped modules remained at the flat level after the move.

---

## 5. Validation results

Commands from the original Phase 2 DoD, re-run from **repository root** on **2026-05-22** (post senior-review report corrections). Honest status per command:

| Command | Status | Notes |
|---------|--------|-------|
| `python -m compileall backend` | **PASSED** (exit 0) | Process exit 0. When using system Python 3.9, `compileall` may log `SyntaxError` under `backend/.venv/` (packages written for 3.11+). **CI uses** `python -m compileall src` from `backend/` (excludes `.venv`). Application `src/` compiles cleanly. |
| `cd backend && ruff check .` | **FAILED** (exit 1) | 16 fixable `I001` import-sort issues (mostly under `tests/`). Not introduced by report corrections. `ruff check src` was clean after Phase 2 move import fixes. |
| `cd backend && mypy .` | **FAILED** (exit 1) | 411 errors in 74 files (includes `tests/`). **CI uses** `mypy src` — see below. |
| `pytest` | **FAILED** | **FAILED_WITH_KNOWN_NON_IMPORT_FAILURES** — 2454 passed, 29 skipped, **2 failed** (~19s with coverage per `pytest.ini`). |

### CI-aligned checks (reference — not in original DoD verbatim)

| Command | Status | Notes |
|---------|--------|-------|
| `cd backend && mypy src` | **PASSED** | `Success: no issues found in 575 source files` — matches `.github/workflows/develop-quality-gate.yml`. |
| `cd backend && ruff check src` | **PASSED** (at Phase 2 completion) | After `ruff check src --fix` during move. |

### `pytest` — failure detail

**FAILED_WITH_KNOWN_NON_IMPORT_FAILURES** — 2454 passed, 29 skipped, 2 failed

- `backend/tests/api/test_supplier_prompt_configs_api.py::test_default_and_model_specific_scopes_are_independent`
- `backend/tests/api/test_supplier_prompt_configs_api.py::test_get_prompt_config_by_id_success`

Failure: `SUPPLIER_PROMPT_CONFIG_INVALID_MODEL` for `gemini-2.0-flash-exp` — not an `ImportError`. SQL Server ODBC unavailable locally (memory fallback). **Not attributed to the use-case move** unless a future bisect proves otherwise.

---

## 6. Behavior-change statement

**No runtime behavior was intentionally changed.** This phase only moved files, updated imports, added empty package `__init__.py` markers, and applied ruff import ordering on affected `src/` files during the move.

Senior-review corrections (this pass) updated **documentation only** and **removed** the one-shot migration script — no application code changes.

---

## 7. Risks remaining

- **`run_aisle_code_scan.py`** still imports `src.infrastructure.code_scanning.image_decode` (not fixed in this phase).
- **Large capture-session modules** unchanged in size (400–500 lines).
- **Duplicate import surfaces** remain (routes + `dependencies.py`).
- **Stale barrel** — root `__init__.py` still exports only inventory create/list.
- **2 API tests** failing locally (supplier prompt config / model catalog / ODBC) — triage separately from modularization.
- **`ruff check .`** may fail on test import order until fixed or CI scope clarified.

---

## 8. Recommended next phase

1. **Merge** after review of move diff (`git diff --find-renames`).
2. **Optional:** `ruff check . --fix` on test import order if `ruff check .` is a merge gate.
3. **Phase 3 (optional):** explicit package re-exports — avoid mega-barrel.
4. **Phase 4:** extract `shared/` helpers to `application/services` where appropriate.
5. **Phase 5:** split multi-class files and fix infrastructure leakage in code scans.

---

## Migration tooling (removed)

The one-shot helper `scripts/move_use_cases_phase2.py` was **removed** before merge per senior review — it must not be re-run after the move (would be destructive). Historical mapping remains in `audit/use-cases-modularization-audit.md` §5.
