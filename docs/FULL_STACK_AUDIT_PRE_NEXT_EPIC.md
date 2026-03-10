# Full Stack Audit — Pre-next-epic Review

**Date:** Pre-next-epic (post–Épica 4, asset upload/list in place)  
**Scope:** Backend (domain, application, api, infrastructure, schema, tests) and frontend (API client, types, InventoryDetail, upload/processing UI, utils).  
**Objective:** Assess whether the implementation is architecturally correct, coherent end-to-end, robust enough for the current product stage, and ready for the next epic (deeper processing/job lifecycle, result views, review flows, evidence visualization).

---

## 1. Executive verdict

**READY WITH MINOR FIXES**

The current full-stack slice respects the intended architecture (api → application/use_cases → ports → infrastructure on the backend; React + TypeScript + centralized API and local state on the frontend). Routes are thin, use cases are framework-agnostic, persistence and storage are behind ports, and error handling (404, 409, 400, 422) is consistent. Upload/list asset flows, aisle processing, and inventory/aisle CRUD behave correctly; tests cover use cases and API wiring for success and key failure cases. Frontend loading states, empty states, and error presentation are coherent, and API contracts align with backend responses.

No critical defects were found. The main follow-up is the **N+1 asset-count pattern** on the frontend (one GET assets call per aisle when loading or refreshing the list). This is acceptable at current scale but should be revisited when inventories grow (e.g. bulk count endpoint or batch loading). A few medium/low items (use-case consistency for “not found”, upload-route file-skip behavior, CreateAisleDialog typings) are documented below as deferrable improvements. Proceeding to the next epic is reasonable; address the minor items in the backlog or as part of the next epic where relevant.

---

## 2. What is correct

**Backend**

- **Layered architecture:** Clear separation: routes depend on use cases and DTOs; use cases depend only on ports (repositories, ArtifactStorage, JobQueue, Clock). No framework types in domain or use cases.
- **Thin routes:** `inventories_v3` limits itself to request/response mapping, dependency injection, and exception → HTTP status (404, 409, 400, 422). Business rules live in use cases.
- **Use cases:** Upload, list assets, start processing, list aisles with status, create inventory/aisle, get inventory — all take simple parameters or commands and return domain entities or raise application errors. No FastAPI or request objects.
- **Persistence:** Repositories are behind ports; SQL and in-memory implementations share the same contract. Schema (inventories, aisles, v3_jobs, source_assets) has appropriate FKs and indexes. SourceAssetRepository validates `uploaded_at` before SQL; storage adapter uses streaming copy and path-traversal checks.
- **Dependency wiring:** Single place in `api/dependencies.py`; SQL vs in-memory and fallback behavior are explicit. Use cases receive repos and services via FastAPI Depends.
- **Error model:** Dedicated application errors (AisleNotFoundError, InventoryNotFoundError, DuplicateAisleCodeError, ActiveJobExistsError, UnsupportedAssetTypeError, EmptyUploadError) mapped consistently in routes.
- **Upload flow:** Non-atomic behavior is documented; partial-upload logging exists; content-type validation and aisle/inventory checks are in place.

**Frontend**

- **Structure:** Centralized API client and types; shared utils (apiErrors, jobStatus, formatDate); page-level state in InventoryDetail; CreateAisleDialog for create flow. Responsibilities are clear.
- **Upload UX:** Helpers (`fetchAssetCountsForAisles`, `getUploadContextFromInput`, `executeAisleUpload`) keep the handler readable; only the row in progress shows “Uploading…” and is disabled.
- **Asset counts:** Counts are loaded for all aisles when the list is loaded or refreshed, avoiding a mixed “— / N file(s)” state when backend has data.
- **Error handling:** `getApiErrorMessage` and `ApiError` used consistently; process and upload errors shown in alerts; 404/409 surfaced appropriately.
- **TypeScript:** Typed API responses and request bodies; status types aligned with backend (InventoryStatus, AisleStatus, JobStatus); SourceAssetSummary documents `storage_path` as backend-only.

**End-to-end**

- **Contracts:** Process returns `job_id`; upload returns `assets`; list aisles includes `latest_job`; list assets returns array. Frontend types match.
- **Tests:** Use-case tests for upload (success, not found, wrong inventory, unsupported type, empty) and list assets; API tests for create/get/list inventories and aisles, process (202/404/409), status, upload (201/404), list assets (200/404), duplicate code, validation. Coverage is meaningful for the current slice.

---

## 3. Issues found

### Critical

- **None.**

### High

- **N+1 asset count requests (frontend)**  
  - **What:** When the aisle list is loaded (initial or refresh), the frontend calls `getAisleAssets(inventoryId, aisleId)` once per aisle (`fetchAssetCountsForAisles`). For large inventories (e.g. 50+ aisles) this means many parallel requests and slower load.  
  - **Why it matters:** As the product scales, this will increase latency and server load without a clear UX benefit.  
  - **Recommendation:** In a future epic, add a backend endpoint that returns asset counts per aisle for an inventory in one call (e.g. `GET .../inventories/{id}/aisles/asset-counts`), or batch the current GETs with a cap. Not blocking for the next epic; document as a backlog item.

### Medium

- **GetInventoryUseCase returns Optional instead of raising**  
  - **What:** `GetInventoryUseCase.execute` returns `Optional[Inventory]`; the route maps `None` to 404. Other use cases (e.g. list assets, create aisle) raise `InventoryNotFoundError` or `AisleNotFoundError` when an entity is missing.  
  - **Why it matters:** Inconsistent “not found” handling: some use cases return None, others raise. Uniform “raise XNotFoundError” would simplify the API layer and make behavior more predictable.  
  - **Recommendation:** Consider changing GetInventoryUseCase to raise `InventoryNotFoundError` when `get_by_id` returns None, and have the route catch it like the others. Deferrable; current behavior is correct.

- **Upload route skips files with no filename and no content_type**  
  - **What:** In `upload_aisle_assets`, the loop `for u in files` appends to `uploaded` only when `u.filename or getattr(u, "content_type", None)` is truthy. Files that have neither are dropped silently.  
  - **Why it matters:** Malformed or empty parts could be ignored without feedback, making debugging harder.  
  - **Recommendation:** Log when a part is skipped, or document that only parts with filename or content_type are accepted. Small change; deferrable.

### Low

- **CreateAisleDialog has no TypeScript declaration**  
  - **What:** The component is implemented in `.jsx`; the linter reports a missing declaration file for the module.  
  - **Why it matters:** Weaker type checking at the boundary and no IDE support for the component’s props.  
  - **Recommendation:** Add a minimal `.d.ts` or convert to `.tsx` when next touching that component. Non-blocking.

- **Frontend does not call GET aisle status**  
  - **What:** The backend exposes `GET .../aisles/{aisle_id}/status` (AisleStatusResponse); the frontend only uses the list-aisles endpoint, which already includes `latest_job` per aisle.  
  - **Why it matters:** The status endpoint is unused by the UI; the frontend type `AisleStatusResponse` was removed as dead. If the next epic adds per-aisle status polling, the type/endpoint can be reintroduced.  
  - **Recommendation:** None for now; keep backend endpoint for future use.

---

## 4. Backend assessment

The backend is in good shape for the next epic.

- **Architecture:** The flow api → application/use_cases → ports → infrastructure is respected. Domain entities are framework-agnostic; use cases orchestrate via ports; infrastructure implements repositories and adapters (storage, job queue, clock).  
- **Correctness:** Upload/list assets validate aisle and inventory, enforce content types, persist metadata and files with clear ownership of timestamps. Aisle processing checks for active jobs and enqueues correctly. Not-found, duplicate-code, and active-job-conflict cases are mapped to the right HTTP status codes.  
- **Persistence and storage:** Schema is consistent with the domain (inventories, aisles, v3_jobs, source_assets). Repositories validate required fields (e.g. `uploaded_at`) and use ordered list where needed (e.g. `list_by_aisle` by `uploaded_at ASC`). Storage adapter uses streaming write and path-traversal protection.  
- **Response composition:** All response building is in the route module via small mappers (`_inventory_to_response`, `_aisle_to_response`, `_asset_to_response`, `_status_response_from_result`). No business logic in DTO construction.

The main improvement to carry into the next epic is **uniform not-found handling** (use-case raises vs route mapping None) and **observability** (logging of skipped upload parts). Neither blocks progression.

---

## 5. Frontend assessment

The frontend is a credible and maintainable base for the next epic.

- **Simplicity:** Single main page (InventoryDetail) for the current flow; dialogs for create; no heavy state management. API client and types are centralized; helpers keep the page readable.  
- **InventoryDetail:** The component handles inventory load, aisle list, asset counts, create aisle, process, and upload. The upload path is factored into helpers (`getUploadContextFromInput`, `executeAisleUpload`, `fetchAssetCountsForAisles`). For the current feature set this is acceptable; if the next epic adds more actions (e.g. review, result views), consider splitting the table/actions into a sub-component or a small hook for “aisle actions.”  
- **Loading and empty states:** Full-page loading for initial inventory; inline loading for aisles; “No aisles yet” is distinct from error alerts. Process and upload show per-row “Starting…” / “Uploading…” and then a single success/error message.  
- **Errors:** `getApiErrorMessage` and `ApiError` are used consistently; alerts are used for process, upload, and aisle load errors without duplication.  
- **TypeScript:** Typed API responses and status enums; `storage_path` documented as backend-only. No dead surface after removing the unused `AisleStatusResponse` from frontend types.

The main follow-up is **reducing N+1 asset-count requests** when the number of aisles grows; this can be done in a later epic with a bulk endpoint or batched loading.

---

## 6. End-to-end alignment assessment

Frontend and backend are aligned well enough to continue safely.

- **Endpoints and DTOs:** List inventories, get/create inventory, list/create aisles, start process, get status, upload assets, list assets — all have matching frontend client methods and types. Process returns `job_id`; upload returns `assets`; list aisles includes `latest_job`; list assets returns an array of source assets.  
- **Status and errors:** Backend returns status as strings (e.g. from enums); frontend uses `InventoryStatus | string`, `AisleStatus | string`, `JobStatus | string` and status helpers. HTTP 404, 409, 400, 422 are thrown as `ApiError` with status and detail; the frontend extracts messages consistently.  
- **Dates:** Backend sends datetime as ISO strings; frontend treats them as `string` (e.g. `created_at`, `updated_at`, `uploaded_at`) and uses `formatDate` for display.  
- **Gaps:** None that block the next epic. The frontend does not use GET aisle status; that endpoint remains available for future polling or detail views.

---

## 7. Readiness checklist

| Criterion | Answer | Justification |
|-----------|--------|----------------|
| Backend architecture is stable enough | **Yes** | Clear layers, thin routes, ports-based use cases, no framework in domain. |
| Backend behavior is correct enough | **Yes** | Upload/list/process and CRUD behave correctly; errors mapped; repos and storage robust for current stage. |
| Frontend structure is maintainable | **Yes** | Central client/types/utils; page state and helpers; no unnecessary complexity. |
| Frontend UX/state handling is coherent enough | **Yes** | Loading, empty, and error states are distinct; process/upload feedback is accurate. |
| API contracts are aligned enough | **Yes** | Request/response shapes and status/error semantics match. |
| Tests are sufficient for this stage | **Yes** | Use-case and API tests cover main flows and important failure cases. |
| No blocking issues remain | **Yes** | No critical or high-severity blockers; N+1 asset count is acceptable for current scale. |
| Safe to continue to next epic | **Yes** | Base is solid; minor fixes can be scheduled in backlog or next epic. |

---

## 8. Blocking fixes before next epic

**None.** The implementation is ready to proceed. Any of the items below can be done in parallel or early in the next epic if desired.

---

## 9. Deferrable improvements

1. **Backend:** Have `GetInventoryUseCase` raise `InventoryNotFoundError` when inventory is missing, and handle it in the route like other not-found cases.  
2. **Backend:** Log (or document) when an upload request part is skipped due to missing filename and content_type.  
3. **Frontend:** Add a bulk asset-count endpoint (or batch loading) and use it when loading/refreshing the aisle list, and add a backlog item for this when scaling.  
4. **Frontend:** Add a `.d.ts` for CreateAisleDialog (or convert to `.tsx`) when next modifying that component.  
5. **Frontend:** If InventoryDetail grows significantly in the next epic (e.g. review, result views), extract aisle table/actions into a sub-component or hook to keep the page maintainable.

---

## 10. Final recommendation

**Proceed to the next epic.** The full-stack slice is architecturally sound, behavior is correct, and contracts are aligned. Address the N+1 asset-count pattern when scaling (e.g. bulk endpoint or batch loading) and treat the other items as backlog or small improvements during the next epic. No blocking fixes are required before continuing.
