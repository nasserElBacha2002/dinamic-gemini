# Frontend cache / mutation — pre-merge checklist

Use this for PRs that touch **TanStack Query**, **`queryKeys`**, **canonicalization**, **`useMutations`**, **review / merge / promote** flows, or **cache patching**.

## Quick checks

- [ ] **Query keys** — New or changed queries use `queryKeys` factories, not literal `['v3', …]` or ad-hoc `'merge-results'` segments outside `api/queryKeys.ts`.
- [ ] **Aisles default table** — Inventory-detail aisles list uses `queryKeys.inventories.aislesListTable(inventoryId)`, not `[...aisles(inventoryId), { page, page_size }]`.
- [ ] **Canonicalization** — List hooks use the same canonical params for **cache key** and **`queryFn`** (Phase 2.1 parity).
- [ ] **Invalidation scope** — Mutations invalidate the **smallest** set of domains that still correct UI; avoid “just in case” global prefixes unless documented.
- [ ] **Context-sensitive reviews** — `useSubmitReviewAction` call sites that know the surface (queue vs aisle results) pass **`strategy`** so Phase 4 + 5 behavior applies.
- [ ] **Merge / refresh** — No pairing **`invalidateQueries` + redundant `refetch()`** for the same resource on one user action (Phase 1).
- [ ] **Patching** — `setQueryData` only for known-safe fields; if unsure, **invalidate** instead of guessing nested server state.
- [ ] **Static check** — Run `npm run check:cache` (from `frontend/`) and fix reported issues. PRs touching `frontend/**` run this in **GitHub Actions** (`frontend-validate` workflow: `check:cache`, `typecheck`, `test:ci`).
- [ ] **Observability (dev)** — With Phase 8 tools, spot-check `window.__DINAMIC_CACHE_OBS__?.getRecent()` after exercising the changed flow; confirm guardrails are quiet unless you expect cold-cache fallbacks.

## If you add a new high-traffic mutation

- [ ] Add **`recordMutationInvalidationsObs`** (or extend observability) if it should be visible next to merge / promote / review.
- [ ] Document intentional broad invalidation in a **one-line comment** on the mutation.

## References

- [`frontend-phase8-cache-observability.md`](./frontend-phase8-cache-observability.md) — dev signals and `window` API.
- [`frontend-phase9-cache-guardrails.md`](./frontend-phase9-cache-guardrails.md) — invariants, script, guardrails.
- [`frontend-cache-update-architecture-phase0-7.md`](./frontend-cache-update-architecture-phase0-7.md) — end-to-end architecture.
