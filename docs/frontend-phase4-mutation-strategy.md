# Frontend Phase 4 — Context-aware mutation strategy (initial pass)

## Scope

- Added a lightweight strategy input for `useSubmitReviewAction`.
- Updated the highest-impact call path (`QuickReviewDrawer`) to pass strategy from context.
- Kept backward compatibility: call sites without strategy keep Phase 3 invalidation behavior.
- Did **not** add `setQueryData`, optimistic updates, or a global strategy registry.

**Follow-up:** Phase 5 adds targeted `setQueryData` / `removeQueries` on top of these strategies (see `docs/frontend-phase5-cache-patching.md`).

## Strategy model

Implemented in `frontend/src/hooks/useMutations.ts`:

- `reviewQueue`
- `aisleResults`
- `detail`
- `undefined` (default fallback = Phase 3 behavior)

## Invalidation behavior by strategy

### `reviewQueue`

- Invalidates:
  - `positionDetail(inventoryId, aisleId, positionId)`
  - `reviewQueue.all`
- Does **not** invalidate:
  - positions list
  - merge-results
  - aisles

**Rationale (review queue context):** `ReviewQueuePage` consumes the global review-queue list (`useReviewQueue`) and the drawer loads position detail only. That screen does not mount aisle positions, merge-results, or inventory aisles queries, so those invalidations were dropped for this strategy to avoid redundant refetches (see comment in `useSubmitReviewAction`).

### `aisleResults`

- Invalidates:
  - `positionDetail(inventoryId, aisleId, positionId)`
  - `positions(inventoryId, aisleId)`
  - `mergeResults(inventoryId, aisleId)`
- Does **not** invalidate:
  - review queue
  - aisles

### `detail`

- Invalidates:
  - `positionDetail(inventoryId, aisleId, positionId)`
  - `positions(inventoryId, aisleId)` (parent list safety)
- Does **not** invalidate:
  - review queue
  - merge-results
  - aisles

### Fallback (`strategy` omitted)

- Preserves Phase 3 behavior:
  - `positionDetail`
  - `positions`
  - `mergeResults`
  - `aisles`
  - `reviewQueue.all`

## Call-site changes

- `QuickReviewDrawer` now derives strategy from `context.returnTo`:
  - `review_queue` -> `reviewQueue`
  - `aisle_results` -> `aisleResults`

This covers required high-impact contexts used by `ReviewQueuePage` and `AislePositionsPage`.

## Phase 5+ deferred

- Cache patching (`setQueryData`) for row-level updates/removals.
- Context-specific strategy expansion beyond `useSubmitReviewAction`.
- Optional detail-page dedicated strategy usage where a standalone detail route uses the same mutation.
