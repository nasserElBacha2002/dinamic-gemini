# Frontend Phase 5 — Targeted cache patching (`setQueryData`)

## Scope

- Extends `useSubmitReviewAction` (Phase 4 strategies) with **local cache updates** after a successful POST `.../reviews`.
- The API returns **no body** (`submitReviewAction` → `void`); patches derive only from the **review request** (`ReviewActionRequest`) and known `review_resolution` strings aligned with backend `PositionReviewResolution`.
- **No** broad optimistic updates before the server responds, **no** global entity store, **no** merge-summary recomputation.

### Conservative patching rules (hardening)

- **Flat fields only** where possible: `needs_review`, `review_resolution`, `qty`, `corrected_quantity`, flat `sku`, `position_code`, `status` for delete. Nested `quantity` blocks are **not** fabricated; the next GET is authoritative for provenance.
- **No-op detection:** if the derived position would match the existing one (same semantics), the implementation returns the **same object reference** and does **not** treat the update as a successful patch — invalidation fallback still runs.
- **Row missing:** if the target `position_id` is not in a cached list, that list is not a “successful” patch — the corresponding `invalidate*` flag stays `true`.
- **Insufficient payload** (e.g. `update_quantity` without `corrected_quantity`, empty SKU/code): no patch; invalidation applies.
- **Delete `positionDetail`:** `removeQueries` for the `positionDetail` prefix clears cached detail for that id (including scoped variants) so the UI does not keep showing a deleted row; a refetch would 404 or be misleading. Other inventories’ keys are unaffected.
- **Pagination counts** after row removal: `total_items` / `total_pages` are **best-effort** local adjustments; server totals under filters may differ until a refetch.

## What gets patched

| Strategy        | `setQueriesData` / `removeQueries` targets | Invalidation fallback when cache missing or row not found |
|----------------|---------------------------------------------|---------------------------------------------|
| `reviewQueue`  | All `reviewQueue` list queries; all `positionDetail` scoped queries for the position | `reviewQueue.all` and/or `positionDetail` prefix |
| `aisleResults` | All `positions` list queries (`positionsList` keys under aisle); all `positionDetail` scoped queries | `positions` / `positionDetail` prefixes **plus always** `mergeResults` |
| `detail`       | Same as aisle results for list + detail | `positions` / `positionDetail` only |
| Fallback       | *(none)* | Phase 3 set: `positionDetail`, `positions`, `mergeResults`, `aisles`, `reviewQueue.all` |

### Row removal vs in-place

- **Review queue list:** `confirm`, `mark_unknown`, `mark_image_mismatch`, `delete_position` **remove** the row from cached pages (and adjust `total_items` / `total_pages` heuristically).
- **Aisle positions list:** only **`delete_position`** removes the row; other actions **patch** the matching `PositionSummary`.
- **Position detail:** non-delete actions **patch** `position`; **`delete_position`** removes cached detail queries when a cached entry existed (`removeQueries`).

### Merge results

- **Never** patched locally (counts/SKUs are not recomputed from the request).
- **`aisleResults`:** always `invalidateQueries(mergeResults)` after patching.
- **`reviewQueue` / `detail`:** merge is not invalidated.

## Why some invalidations remain

- **Empty cache:** if a list or detail query was never loaded, the hook falls back to invalidation so the next navigation still refetches.
- **Row not on cached page:** e.g. queue list cache without the row → invalidate queue.
- **Merge / aggregates:** left to the server.

## Deferred (later phases)

- Optimistic updates before server confirmation.
- Patching `review_actions` audit arrays on detail (would require server IDs).
- KPI band (`ReviewQueueSummary`) precision after row removal; lists may be slightly ahead of summary until a later refetch.
- Generic cache helpers shared across other mutations.

## Files

- `frontend/src/hooks/reviewActionCachePatch.ts` — pure transforms + `QueryClient` patch helpers.
- `frontend/src/hooks/useMutations.ts` — wires strategies to patch + conditional invalidation.

## QA

- Review queue: confirm / edit / delete; verify table and drawer update without full-page refetch when data was already cached.
- Aisle results: quantity/SKU edits; list row and detail; merge strip still refreshes.
- Detail-only flows (if `strategy: 'detail'` is used): list + detail coherence without merge/review-queue churn.
