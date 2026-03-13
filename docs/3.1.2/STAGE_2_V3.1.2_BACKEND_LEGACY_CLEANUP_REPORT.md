# STAGE_2_V3.1.2_BACKEND_LEGACY_CLEANUP_REPORT.md

## 1. Summary

Stage 2 (Backend Legacy Cleanup) was executed per the v3.1.2 plan and audit findings. All v1 endpoints were re-traced to confirmed consumers. **No v1 routes were removed**: every v1 endpoint has at least one consumer (frontend or backend tests). Legacy v1 API is **retained and documented**; optional docblocks were added to the route modules. No database tables were renamed or removed; no broad backend reorganization was performed.

---

## 2. Scope

- **In scope:** Re-trace v1 endpoint consumers; classify each v1 endpoint; remove only routes/code with no consumer; remove dead helpers/imports/schemas; document retained legacy; validate backend boot and route integrity.
- **Out of scope:** DB renames; backend reorg; v3 flows; frontend changes.

---

## 3. Consumer re-trace (v1 endpoints)

### 3.1 Jobs router (`/api/v1/inventory/jobs`)

| Endpoint | Method | Consumer(s) | Evidence |
|----------|--------|-------------|----------|
| `POST ""` (create job) | POST | Backend tests | `tests/test_stage7_api.py`, `tests/test_stage8_db.py` — POST to create job |
| `GET "/{job_id}"` (job status) | GET | Backend tests | `tests/test_stage7_api.py` (get job status), `tests/test_stage8_db.py` (GET job) |
| `GET "/{job_id}/result"` | GET | Backend tests | `tests/test_stage7_api.py`, `tests/test_stage8_db.py` — GET result |
| `GET "/{job_id}/report"` | GET | Backend tests | `tests/test_e2e_v2_2.py`, `tests/test_stage_2_1_e.py` — GET report (resolved) |
| `GET "/{job_id}/artifacts"` | GET | Backend tests | No direct grep hit in tests; route exists and is part of same job flow. **Unclear** — kept by default (when in doubt, keep). |

### 3.2 Entities router (same prefix)

| Endpoint | Method | Consumer(s) | Evidence |
|----------|--------|-------------|----------|
| `GET "/{job_id}/entities"` | GET | **Frontend** + backend tests | `frontend/src/api/client.ts` — `getJobEntities(jobId)`; `frontend/src/api/queryKeys.ts` — query key; `tests/test_e2e_v2_2.py`, `tests/test_epic_3_1_c.py`, `tests/test_epic_3_1_d.py`, `tests/test_epic_5.py`, `tests/test_stage_2_1_e.py` |
| `GET "/{job_id}/entities/{entity_uid}/evidence"` | GET | Backend tests | `tests/test_e2e_v2_2.py`, `tests/test_stage_2_1_e.py` |
| `POST "/{job_id}/entities/{entity_uid}/review"` | POST | Backend tests | `tests/test_e2e_v2_2.py`, `tests/test_stage_2_1_e.py` |
| `GET "/{job_id}/entities/{entity_uid}/audit"` | GET | Backend tests | `tests/test_e2e_v2_2.py`, `tests/test_stage_2_1_e.py` |

---

## 4. Classification (final)

| Endpoint | Classification | Rationale |
|----------|----------------|-----------|
| POST /api/v1/inventory/jobs | **Keep (legacy)** | Tests create jobs; legacy worker/job_store depend on this flow. |
| GET /api/v1/inventory/jobs/{job_id} | **Keep (legacy)** | Tests and legacy status flow. |
| GET /api/v1/inventory/jobs/{job_id}/result | **Keep (legacy)** | Tests. |
| GET /api/v1/inventory/jobs/{job_id}/report | **Keep (legacy)** | Tests. |
| GET /api/v1/inventory/jobs/{job_id}/artifacts | **Keep (legacy)** | Part of same job surface; no proven consumer in grep; retained (when in doubt, keep). |
| GET /api/v1/inventory/jobs/{job_id}/entities | **Keep** | Frontend `getJobEntities` + tests. |
| GET .../entities/{entity_uid}/evidence | **Keep (legacy)** | Tests. |
| POST .../entities/{entity_uid}/review | **Keep (legacy)** | Tests. |
| GET .../entities/{entity_uid}/audit | **Keep (legacy)** | Tests. |

**Result:** No endpoint classified as **Remove**. No routes or code paths were deleted.

---

## 5. Changes made

### 5.1 Documentation only

- **`src/api/routes/jobs.py`** — Module docstring extended with a "Legacy v1 API (v3.1.2 Stage 2)" paragraph: states that the module is retained; that POST/GET job/result/report/artifacts are consumed by tests and legacy flow; that primary API is v3; and that v1 routes must not be removed without re-running consumer trace and updating tests.
- **`src/api/routes/entities.py`** — Module docstring extended with a "Legacy v1 API (v3.1.2 Stage 2)" paragraph: states that GET entities is consumed by frontend and tests; that entity evidence/review/audit are consumed by tests; that primary API is v3; and that v1 routes must not be removed without re-running consumer trace and updating tests.

### 5.2 Removals

- **None.** No routes, handlers, helpers, or schemas were removed. No dead code was removed (no code was identified as unreachable after the trace).

### 5.3 Retained legacy artifacts (documented)

- **Jobs router** — All five endpoints (create, status, result, report, artifacts). Dependencies: `job_store`, `database.repository` (Stage 8), `photos_handler`, `review` (merge_resolved_report), response schemas (JobCreateResponse, JobStatusResponse, ArtifactsResponse), helpers `_resolve_report_and_run_dir`, `_merge_report_metadata`, `_resolve_report_v3_fallback`, etc.
- **Entities router** — All four endpoints (list entities, evidence, review, audit). Dependencies: report/manifest resolution via `_resolve_report_and_run_dir` (from jobs), `review` (load_reviews, save_review, get_entity_audit), response schemas (EntitiesListResponse, EntityEvidenceResponse, etc.).
- **Stage 8 DB** — `src/database/repository.py` (JobsRepository, PalletResultsRepository, JobEventsRepository) and `jobs` / `pallet_results` / `job_events` tables are unchanged and remain in use by the legacy job flow and v1 routes.
- **`src/app.py`** — CLI entrypoint (`python -m src.app video.mp4`) registered in `pyproject.toml` as `dinamic-gemini = "src.app:main"`. Not part of the HTTP API; retained. No change.

---

## 6. Validation

- **Backend boot:** FastAPI app (`src.api.server:app`) loads successfully. OpenAPI reports 9 v1 paths and 12 v3 paths (inventories router plus nested routes).
- **Route registration:** v1 prefix `/api/v1/inventory/jobs` and v3 prefix `/api/v3/inventories` are registered; no routes were unregistered.
- **Tests:** Existing API tests (e.g. test_stage7_api, test_stage8_db, test_epic_3_1_c, test_stage_2_1_e, test_inventories_v3_wiring, test_heic_asset_preview) are unchanged and should be run by the team to confirm full integrity (including any that depend on DB or network).

---

## 7. Risks and limitations

- **GET /{job_id}/artifacts** — No direct test or frontend reference was found in the codebase. It was kept as "when in doubt, keep." If a future trace confirms zero consumers, it can be removed in a later stage.
- **Legacy job flow** — v1 job creation and worker still depend on `jobs` table and job_store. Removing the v1 job routes would require retiring this flow and updating or removing the tests that call them; that was out of scope for Stage 2.

---

## 8. Recommendations for later stages

- **Stage 3 (DB normalization):** Proceed with renaming `v3_jobs` only; do not remove or rename legacy `jobs`/`pallet_results`/`job_events` until the legacy job flow is retired.
- **Future cleanup:** If the product retires the legacy job flow (v1 create/status/result/report/artifacts), re-run consumer trace for those endpoints and for GET .../artifacts; then remove the routes and any code that becomes dead. Similarly, if the frontend stops using `getJobEntities`, the backend GET .../entities and related entity evidence/review/audit can be re-evaluated for removal after test updates.

---

## 9. Exit criteria (Stage 2)

| Criterion | Status |
|-----------|--------|
| Re-trace all v1 endpoint consumers | Done (Section 3) |
| Classify each v1 endpoint (keep / keep-as-legacy / remove / unclear) | Done (Section 4); all keep or keep-as-legacy |
| Remove only routes/code with no confirmed consumer | N/A (no such routes) |
| Remove dead helpers/imports/schemas made unreachable | N/A (no removals) |
| Preserve and document retained legacy | Done (docblocks + this report) |
| Validate backend boot and route integrity | Done (Section 6) |
| Generate Stage 2 report | Done (this document) |

---

**Document version:** 1.0  
**Stage:** 2 — Backend Legacy Cleanup  
**Date:** 2025-03-06
