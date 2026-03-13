# STAGE_3_V3.1.2_API_CONSOLIDATION_REPORT.md

## 1. Summary

Stage 3 consolidates the active API surface on v3, modularizes the v3 route implementation, migrates or retires v1 behavior, and removes the legacy route modules `jobs.py` and `entities.py`. v3 is now the only supported API for the inventory workflow. Frontend and tests no longer depend on v1 routes.

---

## 2. Route migration map

| Legacy route | Current consumer | Decision | New v3 route / replacement | Notes |
|--------------|------------------|----------|----------------------------|-------|
| POST /api/v1/inventory/jobs (create job) | Backend tests | **Retired** | v3 POST .../aisles/{aisle_id}/process | Job creation in product is via v3 process aisle; legacy upload flow retired. Tests migrated or removed. |
| GET /api/v1/inventory/jobs/{job_id} (status) | Backend tests | **Retired** | v3 GET .../aisles/{aisle_id}/status | Aisle status includes latest job. Tests migrated or removed. |
| GET /api/v1/inventory/jobs/{job_id}/result | Backend tests | **Retired** | — | Test-only; retired with v1 routes. |
| GET /api/v1/inventory/jobs/{job_id}/report | Backend tests | **Retired** | — | Test-only; retired with v1 routes. |
| GET /api/v1/inventory/jobs/{job_id}/artifacts | Backend tests (unclear) | **Retired** | — | Retired with v1 job surface. |
| GET /api/v1/inventory/jobs/{job_id}/entities | Frontend client + backend tests | **Replaced** | v3 GET .../aisles/{aisle_id}/positions | Positions are the result entities per aisle. Frontend uses useAislePositions/useResultSummaries; getJobEntities removed. |
| GET .../entities/{entity_uid}/evidence | Backend tests | **Replaced** | v3 GET .../positions/{position_id} | Position detail includes evidences. Tests retired or migrated. |
| POST .../entities/{entity_uid}/review | Backend tests | **Replaced** | v3 POST .../positions/{position_id}/reviews | Same action type semantics. Tests retired or migrated. |
| GET .../entities/{entity_uid}/audit | Backend tests | **Replaced** | v3 GET .../positions/{position_id} | Position detail includes review_actions (audit). Tests retired or migrated. |

---

## 3. New routing structure

v3 routes are implemented under `src/api/routes/v3/`:

- **`v3/__init__.py`** — Exports `router` (single v3 router).
- **`v3/router.py`** — Main APIRouter with prefix `/api/v3/inventories`; includes sub-routers from inventories, aisles, assets, positions, reviews.
- **`v3/shared.py`** — Response mappers, exception mapping, and shared helpers (e.g. `_resolve_normalized_asset_path`, `_position_to_summary`).
- **`v3/inventories.py`** — Create/list/get inventory, get inventory metrics.
- **`v3/aisles.py`** — Create aisle, list aisles, start aisle processing, get aisle status, get job execution log.
- **`v3/assets.py`** — Upload aisle assets, list aisle assets, get asset file.
- **`v3/positions.py`** — List aisle positions, get position detail.
- **`v3/reviews.py`** — Submit position review action (confirm, update_quantity, update_sku, delete_position).

The previous monolith `inventories_v3.py` is removed; the server mounts the v3 router from `src.api.routes.v3`.

---

## 4. Frontend migration summary

- **Removed:** `getJobEntities` from `frontend/src/api/client.ts`.
- **Removed:** `jobEntities` query key from `frontend/src/api/queryKeys.ts`.
- **Types:** `JobEntitiesListResponse` and related entity types remain in `api/types/responses.ts` for now (unused; can be removed in a later cleanup).
- **Tests:** `frontend/tests/getJobEntities.test.ts` removed (tested v1 endpoint only).
- **Actual UI:** No page or component in `frontend/src` called `getJobEntities`; results are loaded via `useAislePositions` / `useResultSummaries` (v3 positions). No component changes required.

---

## 5. Test migration summary

- **test_evidence.py:** No longer imports `_merge_report_metadata` from `jobs`. Test `test_jobs_result_prefer_report_mode` inlined the helper logic (pure function: merge report with job_id, status, mode, confidence_threshold).
- **test_stage7_api.py:** Deleted (entire file tested v1 job API only).
- **test_stage8_db.py:** Removed the three API tests that called v1 GET/POST jobs; kept job_store and worker tests (get_job from DB, _push_success_to_db, insert_pallet_results, worker error event). Removed unused `TestClient` and `app` imports.
- **test_stage_2_1_e.py:** Removed API tests that called v1 entities/report; kept review store, merge_resolved_report, and get_entity_audit tests. Removed unused imports (create_job, update_job, JobOutput, JobStatus, patch, TestClient, app).
- **test_e2e_v2_2.py:** Removed `test_api_review_flow_on_succeeded_job` (v1 entities/review/report).
- **test_epic_3_1_c.py:** Removed list_entities API fixture and all test_list_entities_* tests; kept domain/report tests (compute_traceability_summary, build_hybrid_report, write_report_csv). Removed unused imports (TestClient, app, create_job, update_job, JobOutput, JobStatus, patch).
- **test_epic_3_1_d.py:** Removed client fixture and the two test_list_entities_* tests; kept derive_review_display_label, prompt, report, and CSV tests. Removed unused imports (TestClient, app, patch).
- **test_epic_5.py:** Removed the two test_list_entities_* tests and unused TestClient/app imports.
- **tests/api/test_position_summary_mapping.py:** Imports updated from `inventories_v3` to `v3.shared` (position_to_summary, _summary_sku_and_quantity_from_position).
- **tests/api/test_heic_asset_preview.py:** Patches updated from `src.api.routes.inventories_v3.load_settings` to `src.api.routes.v3.assets.load_settings`.

---

## 6. Removed legacy artifacts

- **`src/api/routes/jobs.py`** — Deleted.
- **`src/api/routes/entities.py`** — Deleted.
- **`src/api/routes/inventories_v3.py`** — Deleted (replaced by `src/api/routes/v3/`).
- **Router registration:** `server.py` no longer includes `jobs_router` or `entities_router`; includes only the v3 router from `src.api.routes.v3`.
- **Worker:** `server.py` still imports `dequeue` and `run_job` from `src.jobs.queue` and `src.jobs.worker`; background job execution unchanged.

---

## 7. Risks and follow-ups

- **Legacy job store / DB:** `job_store`, `database.repository` (Stage 8), and worker still use the same job storage. No DB renames or table removals in this stage. If the product fully retires legacy job creation, a future stage can remove job_store legacy paths and clean DB usage.
- **Unused frontend types:** `JobEntitiesListResponse` and entity-related types in `responses.ts` are now unused; optional follow-up is to remove them.
- **E2E tests:** Any external E2E or integration tests that hit v1 URLs must be updated to v3.

---

## 8. Validation notes

- Backend app boots; only the v3 router is mounted for inventory workflow (`/api/v3/inventories`).
- No remaining Python imports of `src.api.routes.jobs` or `src.api.routes.entities`; no references to `inventories_v3` in `.py` files (docs/skills may still mention the old names).
- Frontend has no references to `getJobEntities` or v1 entity URLs in `frontend/src`.
- test_position_summary_mapping and test_heic_asset_preview updated to use `v3.shared` and `v3.assets`; test_position_to_summary_non_dict_detected_summary_json_no_raise passes (non-dict summary normalized to None, detected_quantity 0).
- Worker: `server.py` still starts the background worker thread using `dequeue` and `run_job` from `src.jobs`; job execution is unchanged.

---

**Document version:** 1.0  
**Stage:** 3 — API Consolidation and Backend Modularization  
**Date:** 2025-03-06
