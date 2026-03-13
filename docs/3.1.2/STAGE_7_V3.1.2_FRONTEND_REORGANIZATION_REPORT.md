# STAGE_7_V3.1.2_FRONTEND_REORGANIZATION_REPORT.md

## 1. Summary

Stage 7 is a **frontend structure audit and compatibility cleanup** on the Dinamic Inventory v3 application. The goal was to validate that the existing layout is sound, align the UI with the stabilized v3 backend surface (including Stage 6 job cancellation), and document/remove legacy artifacts where clearly safe — **without** changing the product UX or performing a large-scale refactor.

The existing frontend already followed a reasonably clean layout (`api/`, `features/`, `hooks/`, `components/`, `pages/`, `utils/`). This stage:

- Confirms and documents the current feature and API boundaries.
- Keeps the existing folder layout, which already matches the desired separation of concerns (see §3 and §4).
- Extends job status presentation helpers so the UI now understands the **full v3 job status set** including `cancel_requested`, `canceled`, and `timed_out`.
- Confirms v3-only API usage in the frontend (no remaining v1 client DTOs or routes).
- Leaves ambiguous or non-harmful legacy pieces in place but clearly documented in this report.

No visual redesign was performed; behavior remains aligned with previous stages.

---

## 2. Previous structure issues

The audit of `frontend/src/` and `frontend/tests/` found the following:

- **API layer:**
  - `src/api/client.ts` contains a v3-only fetch client with clear, route-aligned functions.
  - `src/api/types/` provides DTOs split into `shared.ts`, `requests.ts`, `responses.ts`, `errors.ts`, plus a barrel `index.ts`.
  - `src/api/queryKeys.ts` centralizes TanStack Query key construction.
  - There are **no remaining v1 endpoints** in the client; everything is `/api/v3/...`.

- **Feature organization:**
  - `src/features/results/` contains the results/positions feature: hooks, mappers, selectors, components, and utilities, all grouped by feature.
  - `src/hooks/` exposes generic inventory/aisle/position/query hooks (`useInventories`, `useAisles`, `usePositions`, `useMutations`) with a barrel `index.ts` used by features and pages.
  - `src/components/` holds dialogs and shared UI components, with `components/ui/` for reusable primitives (`PageLayout`, `StatusChip`, `TraceabilityChip`, etc.).
  - `src/pages/` provides route/page-level components (`InventoriesList`, `InventoryDetail`, `AislePositionsPage`, `PositionDetailPage`).

- **Tests:**
  - `frontend/tests/` contains vitest tests for results, traceability, and UI components.
  - Vitest is configured in `vite.config.js` to use `tests/**/*` and a single setup file at `src/test/setup.ts`.

- **Legacy/stale items:**
  - v1-specific DTOs for job entities were already removed from `api/types/responses.ts`; only a short comment remains documenting that decision.
  - There is **no remaining v1 client or query key** usage (confirmed via grep for `getJobEntities`, `entities_v1`, `v1/`).
  - Job status typing (`JobStatus` in `api/types/shared.ts`) had been extended in Stage 6, but the UI helpers in `utils/jobStatus.ts` still only knew about `queued`, `running`, `succeeded`, and `failed`. This created a **partial mismatch** with the backend model for new statuses.

Overall, the main structural issue was **not** folder layout, but **presentation logic lagging behind the extended job status model**.

---

## 3. New structure

No wholesale directory moves were necessary. The existing layout was retained, as it already matches the desired separation:

- `frontend/src/api/`
  - `client.ts` — v3 HTTP client (transport).
  - `types/` — DTOs and shared enums (`shared.ts`, `requests.ts`, `responses.ts`, `errors.ts`, `index.ts`).
  - `queryKeys.ts` — TanStack Query key factory.

- `frontend/src/features/`
  - `results/` — results/positions feature:
    - `types.ts` — visible Result model.
    - `hooks/useResultSummaries.ts` — maps `Position*` DTOs to Result model.
    - `mappers/` — mapping from API DTOs to Result entities.
    - `components/` — result-specific UI (overview + detail).
    - `selectors/`, `utils/`, `constants.ts` — feature-specific logic.

- `frontend/src/hooks/`
  - `useInventories.ts`, `useAisles.ts`, `usePositions.ts`, `useMutations.ts`, `index.ts` — shared domain hooks over the v3 API.

- `frontend/src/components/`
  - `CreateInventoryDialog.tsx`, `CreateAisleDialog.tsx`, `ExecutionLogPanel.tsx`.
  - `components/ui/` — shared UI primitives and layout components.

- `frontend/src/pages/`
  - `InventoriesList.tsx`, `InventoryDetail.tsx`, `AislePositionsPage.tsx`, `PositionDetailPage.tsx`.

- `frontend/src/utils/`
  - Cross-cutting helpers (`jobStatus.ts`, `aisleStatus.ts`, `positionStatus.ts`, `resultRoutes.ts`, `traceability.ts`, etc.).

This structure already **cleanly separates**:

- API transport and DTOs (`api/`).
- Feature logic (`features/results/`).
- Shared domain hooks (`hooks/`).
- Shared UI (`components/ui/`) vs feature UI (`features/results/components/`).
- Pages/routes (`pages/`) and helpers (`utils/`).

Stage 7 therefore focused on **small, targeted changes** rather than a large reshuffle.

---

## 4. Moved files (and why none were needed)

No files were moved in Stage 7. The audit concluded that:

- `api/` cleanly encapsulates transport concerns (`client.ts`), DTOs (`types/`), and query keys (`queryKeys.ts`).
- `features/results/` isolates the results/positions feature (Result model, mappers, hooks, components) behind a clear boundary.
- `hooks/` exposes shared domain hooks used by multiple pages/features.
- `components/` (with `components/ui/`) separates reusable UI primitives from feature-specific views.
- `pages/` holds route-level containers that compose hooks and components.
- `utils/` contains cross-cutting helpers such as status display and routing helpers.
- Tests are already isolated under `frontend/tests/` with a single setup module at `src/test/setup.ts`.

Given this, moving files would have produced churn without materially improving ownership boundaries or readability, so a broader “reorg” was explicitly **not** performed.

---

## 5. Removed legacy artifacts

No additional legacy frontend artifacts were removed in Stage 7. Earlier stages had already:

- Removed v1 job-entities DTOs (`TraceabilitySummary`, `JobEntityListItem`, `JobEntitiesListResponse`) from `api/types/responses.ts`.
- Refocused the frontend on the v3 positions/results model.

The only remaining v1 references in the frontend codebase are **documentation comments** explaining what was removed and why. These comments are valuable for traceability and were kept.

---

## 6. Consolidation work

### 6.1 Job status helpers aligned with v3 JobStatus

**File:** `frontend/src/utils/jobStatus.ts`

**Before:**

- `getJobStatusLabel(status: string)` and `getJobStatusColor(status: string)` only recognized:
  - `queued`
  - `running`
  - `succeeded`
  - `failed`
- Any new backend status values were rendered using a naive capitalization or the default chip color.

**After:**

- The helpers now import and align with the v3 **JobStatus** type:
  - `import type { JobStatus } from '../api/types';`
  - New union type: `type JobStatusLike = JobStatus | string;`
- The label helper recognizes the **full v3 job status set**:
  - `queued` → `Queued`
  - `running` → `Running`
  - `cancel_requested` → `Cancel requested`
  - `canceled` → `Canceled`
  - `timed_out` → `Timed out`
  - `succeeded` → `Succeeded`
  - `failed` → `Failed`
- The color helper maps statuses to MUI `Chip` colors in a way that matches operational semantics:
  - `succeeded` → `success`
  - `failed`, `timed_out` → `error`
  - `running`, `queued` → `primary`
  - `cancel_requested`, `canceled` → `warning`
  - Unknown/unexpected → `default`

The public function signatures remain simple (`JobStatusLike`), so existing call sites that pass `string` values (e.g. `aisle.latest_job.status` in `InventoryDetail.tsx`) continue to work while gaining stricter typing and clearer semantics.

### 6.2 Data-flow patterns (results / positions / reviews)

The audit confirmed that existing data-flow consolidation around the results feature is already in good shape:

- **API DTOs:** `PositionListResponse`, `PositionDetailResponse`, `ReviewActionSummary`, `EvidenceSummary` live in `api/types/responses.ts`, strictly representing backend contracts.
- **Result model:** `features/results/types.ts` defines the visible Result-centric types consumed by the UI.
- **Mappers:** `features/results/mappers/*` map from API DTOs to the Result model.
- **Hooks:** `features/results/hooks/useResultSummaries.ts` and `useResultDetail`:
  - Wrap shared hooks `useAislePositions` / `usePositionDetail` from `src/hooks/usePositions.ts`.
  - Apply mappers to expose **ResultSummary[]** and **ResultDetail** to components.

Because this layering is already clear and feature-local, no additional consolidations or abstractions were introduced in Stage 7.

---

## 7. Compatibility notes

### 7.1 Backend alignment

- **Routes:** The frontend client (`api/client.ts`) only calls v3 routes under `/api/v3/...`, matching the route surface documented in `V3_ROUTE_SURFACE_FINAL.md`. No v1 endpoints remain.
- **DTOs:** `api/types/responses.ts` and `api/types/requests.ts` continue to match the backend schemas (inventory, aisle, positions, review actions, execution log, metrics).
- **Job status:** `JobStatus` in `api/types/shared.ts` already included the Stage 6 statuses (`cancel_requested`, `canceled`, `timed_out`); Stage 7 ensured the UI helpers now understand and present those values explicitly.
- **Position/review flows:** Hooks and mappers around positions/results/reviews were left unchanged and continue to map 1:1 with the backend contracts validated in earlier stages.

### 7.2 UX behavior

- No new buttons, modals, or flows were added in Stage 7.
- The only visible change is improved job status labeling and coloring when the backend reports:
  - `cancel_requested`
  - `canceled`
  - `timed_out`

At the time of v3.1.2, backend timeout handling is still deferred; `timed_out` UI support is intentionally **forward-compatible** and may not be exercised in production yet. In all other cases, the UI behaves as before.

---

## 8. Risks and deferred items

- **Job cancellation UX:** Stage 7 did **not** introduce a new “Cancel job” control in the UI. The backend supports job cancellation, and the frontend now understands the corresponding statuses, but exposing cancellation as an operator action is left for a dedicated UX stage.
- **Test setup location:** Vitest currently uses `src/test/setup.ts` as a shared setup module, while spec files live under `frontend/tests/`. This split is intentional and works well; moving setup into `tests/` was considered but deferred to avoid touching the test harness without clear benefit.
- **Further feature modularization:** `features/results/` is already cohesive. Additional feature modules (e.g. review dashboards, metrics views) could be added later following the same pattern but were out of scope for Stage 7.

---

## 9. Validation notes

- **Type-level alignment:** Confirmed that:
  - `JobStatus` in `api/types/shared.ts` includes `cancel_requested`, `canceled`, and `timed_out`.
  - `AisleJobSummary` and `JobSummary` in `api/types/responses.ts` use `JobStatus | string`.
  - `getJobStatusLabel` / `getJobStatusColor` now accept `JobStatusLike` and handle all of these values.
- **Runtime checks:**
  - Ran a representative frontend test: `npm test -- --run tests/TraceabilityChip.test.tsx` from `frontend/`. Vitest completed successfully, confirming imports and structure remain valid after the change.
- **Structural sanity:**
  - Verified that no new imports point to non-existent modules.
  - Confirmed that no code references v1 endpoints or removed DTOs.

Stage 7 therefore leaves the frontend structurally clear, aligned with the v3.1.2 backend (including job cancellation), and ready for future UX work without incurring unnecessary churn.

