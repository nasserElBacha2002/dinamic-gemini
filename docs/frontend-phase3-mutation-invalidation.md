# Frontend Phase 3 — Mutation invalidation fan-out reduction

## Scope

- Narrow TanStack Query `invalidateQueries` usage in `frontend/src/hooks/useMutations.ts` for high-impact mutations.
- **Not** in scope: mutation strategy layer (Phase 4), `setQueryData`, query key redesign, screen refactors.

## Mutations audited

| Mutation | Previous focus | Change |
|----------|------------------|--------|
| `useSubmitReviewAction` | Broadest fan-out | Remove unused / low-value invalidations; add aisle-scoped aggregate refresh |
| `usePromoteAisleOperationalJob` | Global benchmark + metrics + detail | Narrow benchmark to inventory; drop unused metrics and redundant detail |
| `useRunAisleMerge` | positions + merge-results | **Unchanged** — already minimal |
| `useStartAisleProcessing` | Included `detail` | Removed redundant `detail` invalidation |

## `useSubmitReviewAction`

### Previous behavior

- Position detail (prefix), positions list, merge-results, **aisle-jobs**, **metrics**, **inventory detail**, review queue.

### New behavior

- Position detail (prefix), positions list, merge-results, **aisles** (`GET .../aisles` for this inventory), review queue.

### Rationale

- **Removed `aisle-jobs`:** Review actions do not create or mutate job rows; job list metadata is unchanged.
- **Removed `metrics`:** `useInventoryMetrics` is not mounted anywhere in the app; invalidating those keys only caused unnecessary refetches.
- **Removed `inventory.detail`:** `Inventory` DTO on GET detail does not carry review queue aggregates; aisle-level counts live on **aisles** list.
- **Added `aisles`:** Refreshes `pending_review_positions_count` (and related aisle fields) on Inventory Detail after a review.
- **Not added `inventories.list()`:** Intentionally avoided invalidating every paginated inventories list query to limit fan-out; `pending_review_count` on the home list may lag until natural refetch or navigation. **Phase 4+** can add targeted list invalidation if product requires it.

### Kept

- Position detail + positions + merge-results: direct data affected by the mutation and screens that depend on them.

## `usePromoteAisleOperationalJob`

### Previous behavior

- Aisle jobs, positions, aisles, inventory detail, metrics, benchmark-compare **prefix** `['v3','inventories','benchmark-compare']` (all inventories).

### New behavior

- Aisle jobs, positions, aisles, `benchmarkCompareInventory(inventoryId)` only.

### Rationale

- **Removed `metrics`:** Same as above — no active observers.
- **Removed `inventory.detail`:** Promotion is aisle/run pointer; inventory header payload is unchanged in practice.
- **Narrowed benchmark compare:** `queryKeys.inventories.benchmarkCompareInventory(inventoryId)` invalidates compare payloads for that inventory only, not every compare query in the app.

## `useRunAisleMerge`

- No code change; already invalidates only `positions` and `merge-results` for the aisle.

## `useStartAisleProcessing`

- **Removed** `inventory.detail` invalidation: starting a job updates aisle/job/positions-related state; the inventory header payload from GET detail is unchanged.

## Deferred

- **Context-specific invalidation** (per screen / drawer vs queue): Phase 4.
- **`setQueryData`:** Phase 5.
- **Optional `inventories.list()` after review** for home `pending_review_count`: product decision.
- **Start processing / cancel / retry** job mutations: left as-is; can be revisited in a follow-up pass.

## QA

- After a **review action:** Aisle Results table, Quick Review drawer, merge-results banner, Review Queue, Inventory Detail aisle table.
- After **promote:** Run selector, operational vs benchmark compare for same inventory, positions for that aisle.
