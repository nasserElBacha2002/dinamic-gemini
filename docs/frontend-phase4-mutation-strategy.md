# Frontend Phase 4 — Context-aware mutation strategy (initial pass)

## Scope

- Added a lightweight strategy input for `useSubmitReviewAction`.
- Updated the highest-impact call path (`QuickReviewDrawer`) to pass strategy from context.
- Kept backward compatibility: call sites without strategy keep Phase 3 invalidation behavior.
- Did **not** add `setQueryData`, optimistic updates, or a global strategy registry.

**Follow-up:** Phase 5 adds targeted `setQueryData` / `removeQueries` on top of these strategies (see `docs/frontend-phase5-cache-patching.md`).

## Strategy reference (single source of truth)

| Strategy | Production? | Notes |
|----------|----------------|-------|
| `reviewQueue` | Yes | `QuickReviewDrawer` when `returnTo === 'review_queue'`. |
| `aisleResults` | Yes | `QuickReviewDrawer` when `returnTo === 'aisle_results'`. |
| `detail` | **No — reserved** | Implemented and tested; **not** passed from production UI. Narrower invalidation than `aisleResults` (no merge-results on the strategy path). Use only when a future call site opts in. |
| `undefined` (omitted) | Yes — **fallback** | Phase 3–compatible broad invalidation when no strategy is passed. |

**Phase 4 DoD (strict):** context-sensitive behavior is **fully met** for queue + aisle results; `detail` is an **opt-in extension point**, not an incomplete production branch.

Implemented in `frontend/src/hooks/useMutations.ts` and `reviewActionCachePatch.ts`.

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

### `detail` (reserved)

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

`QuickReviewDrawer` maps `context.returnTo` to `reviewQueue` / `aisleResults` as in the table above. No production path passes `detail`.

## Phase 5+ deferred

- Cache patching (`setQueryData`) for row-level updates/removals.
- Context-specific strategy expansion beyond `useSubmitReviewAction`.
- Optional detail-page dedicated strategy usage where a standalone detail route uses the same mutation.
