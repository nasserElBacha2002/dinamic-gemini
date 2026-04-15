# Frontend Request Baseline (Phase 0) + Tactical Dedup (Phase 1)

> **Superseded as the “current architecture” narrative:** later phases (2–7) and the consolidated note
> [`frontend-cache-update-architecture-phase0-7.md`](./frontend-cache-update-architecture-phase0-7.md) describe
> the system as implemented today. Keep this document for **historical baseline + flow inventory**.

## Scope

- Completed now: Phase 0 (baseline mapping) and Phase 1 (safe dedup of `invalidateQueries + manual refetch`).
- Deferred: Phase 2+ (query-key redesign, canonicalization, mutation strategy, cache patching, broad cache policy tuning).

## Global Query Behavior Baseline

- Query client defaults in `frontend/src/main.tsx`:
  - `staleTime: 30s`
  - `retry: 1`
  - `refetchOnWindowFocus: false`
- Most mutation hooks in `frontend/src/hooks/useMutations.ts` invalidate affected domains on success.
- Several screens also manually call `refetch()` after those mutations, causing duplicate network requests in active views.

## Request Flow Inventory (Critical Flows)

### 1) Create inventory

- Main files: `frontend/src/pages/InventoriesList.tsx`, `frontend/src/hooks/useMutations.ts`.
- Query: `useInventoriesList(...)` (`GET /api/v3/inventories`).
- Mutation: `useCreateInventory` (`POST /api/v3/inventories`).
- Invalidation on success: `queryKeys.inventories.list()`.
- Previous duplication: page-level `refetch()` called right after successful create.

### 2) Open inventory detail

- Main files: `frontend/src/pages/InventoryDetail.tsx`, `frontend/src/hooks/useInventories.ts`, `frontend/src/hooks/useAisles.ts`.
- Queries:
  - `useInventoryDetail(...)`
  - `useAislesList(...)`
  - optional dialogs/modules: visual refs, observability.
- Mutations commonly used from this page:
  - create aisle
  - upload aisle assets
  - start aisle processing
- Invalidation already present in mutation hooks for aisle/detail domains.
- Previous duplication: parent screen forced `aislesQuery.refetch()` through success callbacks even when mutations already invalidated aisles/detail.

### 3) Open aisle positions/results

- Main file: `frontend/src/pages/AislePositionsPage.tsx`.
- Queries:
  - `useResultSummaries` (positions list)
  - `useAisleJobsList`
  - `useAisleMergeResults`
  - plus detail query inside quick review drawer.
- Mutations:
  - `useRunAisleMerge`
  - `usePromoteAisleOperationalJob`
  - review action mutations via drawer.
- Invalidation already present in mutation hooks for positions/jobs/merge/detail/metrics.
- Previous duplication:
  - merge flow triggered `refetch()` for positions immediately after merge mutation invalidated positions.
  - promote flow manually called `refetch()` and `aisleJobsQuery.refetch()` after mutation already invalidated both domains.

### 4) Execute review action

- Main files: `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx`, `frontend/src/hooks/useMutations.ts`.
- Mutation: `useSubmitReviewAction`.
- Invalidation fan-out (positions detail/list, merge results, aisle jobs, metrics, inventory detail, review queue).
- No immediate tactical dedup applied in this pass; broad fan-out reduction is Phase 3 scope.

### 5) Run merge

- Main files: `frontend/src/pages/AislePositionsPage.tsx`, `frontend/src/hooks/useMutations.ts`.
- **Update (post Phase 7 closure pass):** mutation invalidates **positions** only; merge-results are refreshed with a **single** `queryClient.fetchQuery` after `mutateAsync` on the page (no `invalidateQueries` + `refetch` duplicate GET).
- Tactical dedup applied now: removed manual positions `refetch()` after mutation.

### 6) Promote operational job

- Main files: `frontend/src/pages/AislePositionsPage.tsx`, `frontend/src/hooks/useMutations.ts`.
- **Current `usePromoteAisleOperationalJob`:** patches or invalidates aisle jobs; invalidates positions, aisles list, and benchmark-compare-under-inventory (see hook comments).
- Tactical dedup applied now: removed manual positions/jobs refetch after mutation.

### 7) Open metrics/analytics

- Main files: `frontend/src/features/analytics/hooks.ts`, `frontend/src/hooks/useAisles.ts`.
- Compare/metrics queries are keyed by inventory/aisle/job pair; several views still use manual refetch patterns.
- Deferred for later phase to avoid mixing broader analytics behavior in this tactical pass.

### 8) Drawers/dialogs that fetch data

- Main files:
  - `frontend/src/components/AisleObservabilityDialog.tsx`
  - `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx`
- Observability dialog has manual refresh controls by design (operator action). It can call parent refresh callback.
- Tactical dedup applied now: stopped wiring parent aisle refetch callback from `InventoryDetail`, reducing duplicate refresh pressure after job mutations.

## Duplicate Request Suspects

## Confirmed and fixed now

- `InventoriesList` create success:
  - invalidation + manual `refetch()`.
- `InventoryDetail` upload/process/create-aisle success callbacks:
  - mutation invalidation + forced parent `aislesQuery.refetch()`.
- `AislePositionsPage` promote success:
  - mutation invalidation + manual positions/jobs refetch.
- `AislePositionsPage` merge success:
  - mutation invalidation + manual positions refetch.
- `InventoryDetail` -> `AisleObservabilityDialog`:
  - parent aisles refetch callback removed to avoid extra parent request bursts during dialog refresh/mutation flows.

## Confirmed/suspected but deferred

- `useSubmitReviewAction` invalidation fan-out may be broader than necessary for each context (likely high backend load under rapid review).
- Analytics compare screens use explicit refetch behavior that may overlap with invalidations in some transitions.
- Some query keys still include object values (`['reviewQueue', listQuery]`, inventories list object key). Stable enough in many paths, but canonicalization belongs to Phase 2.

## Baseline Metrics (Static Estimate)

- Create inventory interaction:
  - before: ~2 requests (POST + list refetch; invalidation may also trigger active observer fetch)
  - after Phase 1 fix: typically ~1 follow-up fetch path (invalidated list observer)
- Inventory detail mutations (create aisle / upload / process):
  - before: mutation + explicit aisles refetch + invalidation-triggered refetch
  - after: mutation + invalidation-triggered refetch
- Aisle promote flow:
  - before: mutation + invalidation-triggered refetches + explicit positions/jobs refetch
  - after: mutation + invalidation-triggered refetches only
- Aisle merge flow:
  - before: mutation + explicit positions/aisles/merge-results refetch
  - after: mutation + explicit aisles + merge-results refresh (positions manual refresh removed)

## Phase 1 Changes Implemented

- `frontend/src/pages/InventoriesList.tsx`
  - Removed `refetch()` in create-success path; rely on mutation invalidation.
- `frontend/src/pages/InventoryDetail.tsx`
  - Removed `onAfterSuccess` aisle refetch callbacks for upload/process flows.
  - Removed explicit aisle refetch on create-aisle success.
  - Removed `onAislesInvalidate` callback wiring to observability dialog.
- `frontend/src/pages/AislePositionsPage.tsx`
  - Merge flow: removed manual positions `refetch()` from post-mutation refresh block.
  - Promote flow: removed manual positions/jobs refetch after successful promotion.

## Why these fixes are safe

- All removed calls were secondary refresh paths where corresponding mutation hooks already invalidate the same resources.
- Active query observers still refresh from invalidation, preserving user-visible correctness.
- No endpoint contracts, payload shapes, or query keys were changed in this phase.

## Deferred for Later Phases

- Phase 2: query-key canonicalization and object-key stabilization.
- Phase 3: reduce review mutation invalidation fan-out by context and data dependency.
- Phase 4+: mutation strategy layer and `setQueryData` cache patching.
- Broad stale/refetch policy tuning by endpoint volatility.
