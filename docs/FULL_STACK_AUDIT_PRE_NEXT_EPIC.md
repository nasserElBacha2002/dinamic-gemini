# Full Stack Audit — Pre-next-epic Review

**Dinamic Inventory v3.0**  
**Scope:** Backend (v3 inventories, aisles, processing, jobs) + Frontend (React/TS/MUI, inventory detail, aisle processing UI).  
**Audit style:** Evidence-based; strict on architecture and maintainability; no approval by default.

---

## 1. Executive verdict

**READY WITH MINOR FIXES**

The current slice respects the intended architecture end-to-end: thin API routes, framework-agnostic use cases, clear ports and infrastructure, and a simple frontend with centralized error handling and typed models. Aisle processing flows (start job, batch job loading, conflict handling) are correct and tested. The main gaps are a small inconsistency in where application exceptions live and a few low-severity items that should be fixed or documented before the next epic so the base stays clean. None of these are blocking for moving forward if addressed in a short follow-up.

---

## 2. What is correct

**Backend**
- **Layering:** `api → application/use_cases → ports → infrastructure` is respected. Routes only depend on use cases and domain/schema types; they do not touch repositories or infrastructure directly.
- **Thin routes:** `inventories_v3` handlers: call one use case, map result via `_inventory_to_response` / `_aisle_to_response` / `_status_response_from_result`, map application exceptions to HTTP (404/409). No business logic in the route module.
- **Use cases:** No FastAPI or HTTP imports. They depend only on ports (repositories, JobQueue, Clock) and domain entities; orchestration and exception semantics are clear (e.g. `StartAisleProcessingUseCase`, `ListAislesWithStatusUseCase`).
- **Persistence:** Repositories are behind ports. SQL and in-memory implementations for Inventory, Aisle, and Job exist; v3_jobs and aisles/inventories schema are consistent with domain. Batch `get_latest_by_targets` is implemented in both SQL (ROW_NUMBER) and memory, avoiding N+1 in list aisles.
- **Processing flow:** Start aisle processing: load aisle, validate inventory ownership, check for active job (QUEUED/RUNNING), enqueue, persist Job, mark aisle queued, save aisle. Conflict and not-found cases raise application exceptions and are mapped to 404/409 in the route.
- **Response composition:** Response DTOs (InventoryResponse, AisleResponse, AisleJobSummary, JobSummary, AisleStatusResponse) are built in the route from domain/result types; composition is localized and consistent.
- **Queue adapter:** V3JobQueueAdapter implements JobQueue port; docstrings state that only job_id is enqueued and v3 consumption is deferred; structured logging is in place.

**Frontend**
- **Structure:** Clear separation: API client, types, utils (apiErrors, jobStatus, formatDate), pages, dialogs. No heavy state management; local state and callbacks are sufficient for the current flows.
- **Error handling:** `getApiErrorMessage(error, fallback)` centralizes extraction for string detail, FastAPI validation array `[{ msg }]`, and generic errors. Used in InventoryDetail, InventoriesList, CreateAisleDialog, CreateInventoryDialog.
- **Typing:** `JobStatus` and `JOB_STATUSES` align with backend; `AisleJobSummary` and `JobSummary` use `JobStatus | string`. Inventory and Aisle types match API responses (optional dates, status as string).
- **Processing UX:** Success message is shown only after both `startAisleProcessing()` and `loadAisles()` succeed; on refresh failure the error path runs and no success is shown.
- **Optional onError:** CreateAisleDialog has optional `onError`; callers that do not need parent-level error handling do not pass it (e.g. InventoryDetail).
- **Status display:** `getJobStatusLabel` and `getJobStatusColor` give consistent job status chips; aisle status remains a simple Chip for now.

**End-to-end**
- API contracts: Backend returns ISO datetimes, string statuses; frontend types use string for dates and status. Process endpoint returns `{ job_id }`; list aisles returns aisles with optional `latest_job` (id, status, updated_at). Frontend does not call GET aisle status; list + latest_job is sufficient for current UI.
- Error semantics: 404/409/422 and `detail` (string or validation array) are consumable by the frontend via `getApiErrorMessage` and `ApiError.data`.

**Tests**
- Backend: API wiring tests cover get/list/create inventory, get/list/create aisle, 404/409/422, start process (202, 404, 409), get aisle status, list aisles with latest_job. Use case tests cover StartAisleProcessing (success, aisle not found, wrong inventory, active job), GetAisleProcessingStatus, ListAislesWithStatus (with and without jobs, inventory not found). Repository tests exist for SQL and in-memory where relevant.

---

## 3. Issues found

### Critical
- **None.**

### High
- **None.**

### Medium

**M1. Application exception location inconsistency**  
- **What:** `InventoryNotFoundError` (and `DuplicateAisleCodeError`) are defined in `src/application/use_cases/create_aisle.py`, while `AisleNotFoundError` and `ActiveJobExistsError` are in `src/application/errors.py`. Two use cases (`list_aisles_by_inventory`, `list_aisles_with_status`) import `InventoryNotFoundError` from `create_aisle`. The route imports `InventoryNotFoundError` and `DuplicateAisleCodeError` from `create_aisle` and `AisleNotFoundError`/`ActiveJobExistsError` from `application.errors`.  
- **Why it matters:** Two sources of “application errors” make it harder to see the full set of API-mapped exceptions and to evolve them (e.g. adding codes or logging) in one place.  
- **Recommendation:** Move `InventoryNotFoundError` and `DuplicateAisleCodeError` into `src/application/errors.py`, re-export or import them from there in `create_aisle` for backward compatibility, and update all imports (routes, list_aisles_by_inventory, list_aisles_with_status) to use `application.errors`. No change to behavior or HTTP mapping.

### Low

**L1. Client `handleResponse` message when `detail` is an array**  
- **What:** In `frontend/src/api/client.ts`, when `response.ok` is false and `data.detail` is not a string (e.g. FastAPI validation array), the thrown `ApiError` gets `message` from `text` (first 200 chars) or `statusText`, so `ApiError.message` can be unhelpful.  
- **Why it matters:** Any code that only reads `err.message` would see raw JSON or “Unprocessable Entity” instead of the first validation message.  
- **Recommendation:** Either extend `handleResponse` to set a first validation message when `detail` is an array (e.g. `detail[0]?.msg`), or document that consumers must use `getApiErrorMessage(err, fallback)` for user-facing text. Current usage uses `getApiErrorMessage` everywhere in the touched UI, so behavior is correct; this is a robustness/documentation improvement.

**L2. Unused type `AisleStatusResponse` in frontend**  
- **What:** `frontend/src/api/types.ts` still defines `AisleStatusResponse`; the client no longer has `getAisleStatus()` so the type is unused.  
- **Why it matters:** Dead type surface; minor.  
- **Recommendation:** Keep the type if the next epic will add status polling or a status view; otherwise remove it. Document the decision in a short comment.

**L3. No frontend automated tests**  
- **What:** There are no unit or integration tests for the React components or the API client.  
- **Why it matters:** Refactors and new features have no safety net on the frontend.  
- **Recommendation:** Deferrable. Add at least API client or key-page tests when the next epic expands UI or API usage.

---

## 4. Backend assessment

The backend is in good shape for the next epic.

- **Architecture:** Clear separation of API, application, and infrastructure; use cases are pure orchestration; persistence and queue are behind ports. Response composition is contained in the route module.
- **Correctness:** Aisle processing (start, conflict, not-found), list aisles with latest job (batch load), and status endpoint behave as intended. Repositories handle empty inputs and ordering; SQL job repo uses a single batch query for `get_latest_by_targets`.
- **Schema and persistence:** v3_jobs and aisles/inventories match domain; constraints (e.g. UNIQUE inventory_id+code) support business rules. Job status values are consistent (queued/running/succeeded/failed).
- **Tests:** API and use case tests cover success and failure paths; no critical gap for the current slice.

The main improvement is to centralize application exceptions (M1) so the next epic can extend error handling or logging in one place without hunting across modules.

---

## 5. Frontend assessment

The frontend is a credible and maintainable base for the next epic.

- **Simplicity:** Single-page flows, local state, no unnecessary abstractions. Pages own loading/error state; dialogs are self-contained with optional callbacks.
- **Responsibilities:** API client is the only place that talks to the backend; types reflect API contracts; utils (apiErrors, jobStatus, formatDate) are focused and reused.
- **UX and state:** Loading states (inventory, aisles, process button) are clear; empty state (“No aisles yet”) is distinct from errors; process success is shown only after a successful refresh; API errors are shown via a single helper.
- **TypeScript:** Typed responses and requests; `JobStatus` and status helpers improve safety and consistency. No critical typing gaps in the audited flow.

Adding frontend tests (L3) in a later epic will improve confidence as the UI grows.

---

## 6. End-to-end alignment assessment

Frontend and backend are aligned well enough to continue safely.

- **Contracts:** Endpoints used by the frontend (inventories CRUD, aisles CRUD, POST process) return shapes that match the frontend types (ids, status strings, optional `latest_job` with id/status/updated_at, `job_id` for process). GET aisle status is implemented and tested on the backend but not called from the client by design.
- **Status values:** Backend job status enum (queued, running, succeeded, failed) matches frontend `JOB_STATUSES` and status helpers. Aisle and inventory statuses are string-based on both sides.
- **Errors:** 404/409/422 and `detail` (string or validation array) are handled by `getApiErrorMessage`; the frontend can show consistent messages.
- **No contract mismatch** was found that would block the next epic. Keeping `AisleStatusResponse` or removing it (L2) is a small, local decision.

---

## 7. Readiness checklist

| Criterion | Answer | Justification |
|----------|--------|----------------|
| Backend architecture is stable enough | **Yes** | Clear layers, thin routes, use cases and ports in place. |
| Backend behavior is correct enough | **Yes** | Processing, conflicts, not-found, and list-with-job are correct and tested. |
| Frontend structure is maintainable | **Yes** | Clear separation of client, types, utils, pages, dialogs. |
| Frontend UX/state handling is coherent enough | **Yes** | Loading, errors, empty state, and process feedback are consistent. |
| API contracts are aligned enough | **Yes** | Types and responses match; error semantics are usable. |
| Tests are sufficient for this stage | **Yes** | Backend API and use cases are well covered; frontend tests deferred. |
| No blocking issues remain | **Yes** | Only medium (M1) and low (L1–L3) items; none block the next epic. |
| Safe to continue to next epic | **Yes** | After addressing M1 (and optionally L1/L2), the base is clean to build on. |

---

## 8. Blocking fixes before next epic

**None.** The verdict is READY WITH MINOR FIXES; no change is strictly blocking. Recommended before or at the very start of the next epic:

- **M1:** Move `InventoryNotFoundError` and `DuplicateAisleCodeError` to `src/application/errors.py` and update all imports so all application exceptions live in one module.

---

## 9. Deferrable improvements

- **L1:** Improve `handleResponse` so that when `detail` is a validation array, `ApiError.message` is set to the first validation message (or document that `getApiErrorMessage` must be used for display).
- **L2:** Decide whether to keep or remove `AisleStatusResponse` and add a one-line comment explaining the decision.
- **L3:** Add frontend tests (e.g. API client or critical paths) when the next epic adds features or refactors UI.
- **Optional:** Expose `retryable` on the aisle in the API if the next epic needs it for UX (e.g. “Retry” visibility); domain and schema already support it.

---

## 10. Final recommendation

- **Proceed to the next epic**, with a short follow-up to apply **M1** (centralize application exceptions in `application/errors.py`). That keeps the codebase consistent and makes it easier to extend error handling or logging later.
- Optionally do **L1** and **L2** in the same pass; **L3** can wait until the next epic adds more frontend behavior.
- No need to hold the next epic for these items; they can be done in parallel or in the first sprint of the new epic.
