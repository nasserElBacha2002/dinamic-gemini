# Frontend Phase 6 — selective mutation expansion

## Scope

- Applied Phase 4/5 principles to **two** additional mutations with high confidence:
  - `useCreateAisle`
  - `usePromoteAisleOperationalJob`
- Kept all other candidate mutations unchanged when response data was not sufficient for safe patching.
- Added one small mutation helper module: `frontend/src/hooks/mutationCachePatch.ts`.

## Candidate review

- `useCreateAisle` — **implemented**
  - Response returns full `Aisle`.
  - Inventory Detail uses one default aisle list query (`page=1,page_size=200`), so local insertion is safe in common case.
- `usePromoteAisleOperationalJob` — **implemented**
  - Response returns `operational_job_id`.
  - Cached `AisleJobsListResponse` has explicit `operational_job_id` and per-job `is_operational`.
- `useStartAisleProcessing` — **deferred**
  - Response returns only `job_id`; no authoritative aisle/job summary for safe list patching.
- `useRunAisleMerge` — **left invalidation-driven**
  - Merge response has counters, but visible merge/results payload needs server recomputation and is not safely patchable from these counters alone.

## Implemented behavior

## `useCreateAisle`

- Previous:
  - Always invalidated `inventories.aisles(inventoryId)` and `inventories.detail(inventoryId)`.
- New:
  - Tries to patch cached default aisle list (`page=1,page_size=200`) by prepending the created aisle.
  - Keeps invalidation fallback if:
    - no cache exists,
    - query is not default list shape,
    - aisle already exists in cache,
    - cached page is full.
  - Still invalidates `inventories.detail(inventoryId)` (aggregate/detail consistency).

## `usePromoteAisleOperationalJob`

- Previous:
  - Always invalidated `aisleJobs`, `positions`, `aisles`, `benchmarkCompareInventory`.
- New:
  - Tries to patch cached aisle-jobs queries by:
    - setting `operational_job_id`,
    - flipping each job’s `is_operational` by id.
  - Falls back to `aisleJobs` invalidation when no patchable cache exists.
  - Keeps existing invalidations for `positions`, `aisles`, and `benchmarkCompareInventory`.

## Safety notes

- Patches are intentionally local and conservative.
- No optimistic updates were added.
- No aggregate/KPI recomputation is done in the client.
- Fallback invalidation remains the safety net.

## Test coverage

- New tests: `frontend/tests/useMutations.phase6.test.tsx`
  - create-aisle patched path + fallback path
  - promote patched path + fallback path
  - unrelated inventory cache remains unchanged for promote patch

## Deferred for later phases

- Start-processing cache patching pending richer response contract.
- Merge-flow cache patching pending authoritative merge/result response shape for row-level updates.
