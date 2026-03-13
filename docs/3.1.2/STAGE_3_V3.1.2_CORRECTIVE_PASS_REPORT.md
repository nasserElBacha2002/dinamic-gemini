# STAGE_3_V3.1.2_CORRECTIVE_PASS_REPORT.md

## 1. Summary

This report documents a **corrective pass** over the already-implemented Stage 3 (API consolidation and backend modularization) of Dinamic Inventory v3.1.2. The goal was to review the six primary technical risks introduced by the migration and apply only justified corrections to leave Stage 3 in a robust state.

**Scope:** Audit six concerns → apply minimal, high-value fixes → validate integrity → document. No architectural rollback; v3 remains the only supported inventory API surface.

---

## 2. Concern-by-concern assessment

### Concern 1 — Did we remove useful test coverage instead of only legacy-route coverage?

**Assessment:** No missing behavior-level coverage identified.

**Evidence:**
- Removed tests (test_stage7_api, v1 blocks in test_stage_2_1_e, test_epic_3_1_c, test_epic_3_1_d, test_epic_5, test_e2e_v2_2) targeted v1 HTTP endpoints (GET/POST `/api/v1/inventory/jobs/...`, entities, report).
- Equivalent behavior is covered as follows:
  - **Review store / merge / audit:** Still tested in `test_stage_2_1_e.py` (review_store load/save, merge_resolved_report, get_entity_audit).
  - **Traceability summary computation:** Still tested in `test_epic_3_1_c.py` (compute_traceability_summary, compute_traceability_summary_from_entity_dicts, build_hybrid_report, write_report_csv).
  - **Display label / report / CSV:** Still tested in `test_epic_3_1_d.py` and `test_epic_5.py` (derive_review_display_label, prompt enrichment, build_hybrid_report, write_report_csv).
  - **v3 positions and reviews:** Covered by `test_aisles_v3_wiring.py` (list positions, position detail 404) and `test_review_actions_api.py` (POST reviews, GET position detail with review_actions).

**Action taken:** None. Removed tests were deprecated-route coverage; behavior-level coverage exists at domain or v3 API level.

---

### Concern 2 — Did the migration lose semantically important job-level access?

**Assessment:** No semantic gap; no new job-level endpoint added.

**Evidence:**
- v1 exposed: GET job status by `job_id`, GET result/report/artifacts by `job_id`.
- v3 exposes: GET `.../aisles/{aisle_id}/status` (includes `latest_job`), GET `.../aisles/{aisle_id}/jobs/{job_id}/execution-log`.
- Frontend flow: Start processing → receives `job_id` in `ProcessAisleResponse` → polls aisle status (which includes latest job) → can fetch execution log by `job_id` when needed. Caller always has `inventory_id` and `aisle_id` from context.
- No use case found where a caller has only `job_id` and needs job status or detail in isolation without aisle context.

**Action taken:** None. Aisle status + execution log are sufficient; adding a standalone GET job-by-id would duplicate context already available via aisle status.

---

### Concern 3 — `result.products[0]` assumption in position detail

**Assessment:** Real risk; fixed.

**Evidence:**
- `GetPositionDetailUseCase` returns `products` from `product_record_repo.list_by_position(position_id)`.
- Port defines `Sequence[ProductRecord]` with no ordering guarantee.
- SQL implementation orders by `created_at ASC, id ASC`; in-memory implementation returns dict values (unordered).
- Using `result.products[0]` without a defined order could be non-deterministic when multiple products exist.

**Action taken:** In `src/api/routes/v3/positions.py`, corrected_quantity is now derived from a **deterministic** “display primary” product: products are sorted by `(created_at, id)` and the first is used. A short comment documents that the use case does not guarantee order and explains the choice.

---

### Concern 4 — Leftover frontend dead types after v1 removal

**Assessment:** Real dead code; removed.

**Evidence:**
- `JobEntitiesListResponse`, `JobEntityListItem`, and `TraceabilitySummary` in `frontend/src/api/types/responses.ts` were only used by the removed `getJobEntities` client.
- Grep showed no remaining imports of these three types in the frontend codebase.
- `ApiTraceabilityStatus` and `TRACEABILITY_STATUSES` remain in use (TraceabilityChip, traceabilityDisplay, utils/traceability).

**Action taken:** Removed the three unused interfaces and the “v1 Job entities” section from `responses.ts`, and added a one-line comment that v1 job-entities types were removed in Stage 3 and that `ApiTraceabilityStatus` remains for position/result UI.

---

### Concern 5 — `shared.py` becoming a new hidden monolith

**Assessment:** Acceptable as-is; no split.

**Evidence:**
- `src/api/routes/v3/shared.py` is ~400 lines and contains: response mappers (inventory, aisle, status, asset, position, evidence, review), exception mapping, review handlers (confirm, update_quantity, update_sku, delete), HEIC resolution, and position-summary helpers.
- All are “v3 route layer” helpers used by the v3 route modules; no unrelated domains.
- Splitting would add several small modules and more import paths for limited maintainability gain.

**Action taken:** None. File remains a single, cohesive helper module for the v3 route layer. If it grows further (e.g. >500 lines or clearly separate domains), a future split can be considered.

---

### Concern 6 — `aisles.py` potentially mixing CRUD and processing/job concerns

**Assessment:** Coherent; no split.

**Evidence:**
- `aisles.py` contains: create aisle, list aisles, start aisle processing, get aisle status, get job execution log.
- All are “aisle and its processing” from the same resource tree: `/api/v3/inventories/{id}/aisles` and nested process/status/execution-log under an aisle. Execution log is already nested under `.../aisles/{aisle_id}/jobs/{job_id}/execution-log`.

**Action taken:** None. One module per resource subtree is acceptable; no over-engineering.

---

## 3. Code changes applied

| File | Change |
|------|--------|
| `src/api/routes/v3/positions.py` | Derive `corrected_quantity` from a deterministic “display primary” product: sort `result.products` by `(created_at, id)` and use the first. Comment added documenting that the use case does not guarantee order. |
| `frontend/src/api/types/responses.ts` | Removed unused v1 job-entities types: `TraceabilitySummary`, `JobEntityListItem`, `JobEntitiesListResponse`. Replaced block with a short comment. |

No other files modified. No new endpoints, no new test files, no split of `shared.py` or `aisles.py`.

---

## 4. Test coverage adjustments

- **Restored:** None. No behavior-level coverage was judged missing.
- **Kept removed:** All v1-route-only tests remain removed; domain and v3 API tests are sufficient.
- **Deemed unnecessary:** No additional v3 tests added; existing `test_aisles_v3_wiring` and `test_review_actions_api` already cover positions list/detail and review submission.

---

## 5. API semantic validation

- **Job vs aisle access:** Supported workflow is aisle-centric (start process → poll aisle status → optional execution log by job_id under that aisle). No standalone job-by-id endpoint required.
- **Position detail:** Corrected_quantity is now derived in a deterministic way from products; behavior is stable across backends (SQL vs in-memory).
- **v3 surface:** Unchanged; no new routes, no removal of routes. Only one route handler implementation detail (primary product selection) was corrected.

---

## 6. Remaining follow-ups

- **Legacy job store / DB:** Unchanged; still used by the worker. Out of scope for this corrective pass.
- **E2E / external tests:** Any external or E2E tests that still hit v1 URLs must be updated to v3 in a separate pass.
- **shared.py / aisles.py size:** Monitor; split only if they grow or responsibilities clearly diverge.

---

**Document version:** 1.0  
**Stage:** 3 corrective pass  
**Date:** 2025-03-06
