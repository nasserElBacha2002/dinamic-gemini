# Frontend cache-update architecture (Phases 0–9)

This note summarizes the current frontend data-update model after optimization Phases 0 through 9.

## System shape

- **Query identity:** all high-traffic list/detail queries use `queryKeys` + canonicalized params.
- **Mutation behavior:** each mutation follows one of two explicit paths:
  - conservative local cache patching when state is known
  - fallback invalidation when patching is uncertain or cache is absent
- **Manual merge (`useRunAisleMerge`):** positions are invalidated in the mutation; merge-results are refreshed from `AislePositionsPage` via **one** `fetchQuery` after success (no overlapping invalidate + UI `refetch` for that resource).
- **Review actions:** strategy-driven (`reviewQueue` / `aisleResults` / `detail` / fallback) with shared orchestration.

## What each phase established

- **Phase 0:** baseline request map and duplicate suspects.
- **Phase 1:** removed obvious `invalidateQueries + refetch()` duplication.
- **Phase 2/2.1:** key canonicalization and key/request parity in priority hooks.
- **Phase 3:** narrowed invalidation fan-out on critical mutations.
- **Phase 4:** added context-aware strategy for `useSubmitReviewAction`.
- **Phase 5 (+ hardening):** introduced conservative `setQueryData` patching with no-op detection and fallback correctness.
- **Phase 6:** expanded the model to selected high-ROI mutations (`useCreateAisle`, `usePromoteAisleOperationalJob`).
- **Phase 7:** consolidated helper responsibilities and conventions (this pass).
- **Phase 8:** lightweight **dev observability** (ring buffer + optional `console.debug` + `window.__DINAMIC_CACHE_OBS__`) for review cache outcomes, non-review patches, key mutation invalidations, and merge `fetchQuery` — see [`frontend-phase8-cache-observability.md`](./frontend-phase8-cache-observability.md).
- **Phase 9:** **guardrails** — static `npm run check:cache` script, dev **warnings** on top of Phase 8 events, invariant tests, and a [**pre-merge checklist**](./frontend-cache-data-pre-merge-checklist.md) — see [`frontend-phase9-cache-guardrails.md`](./frontend-phase9-cache-guardrails.md).

## Current helper organization

- `frontend/src/hooks/reviewActionCachePatch.ts`
  - review-action pure transforms (`applyReviewActionToPositionSummary`)
  - review-action cache patch operations (`patchCachesFor*Strategy`)
  - **central orchestration** for post-success behavior:
    - `applySubmitReviewActionCacheEffects(...)`
- `frontend/src/hooks/mutationCachePatch.ts`
  - non-review mutation helpers (Phase 6):
    - `patchCreateAisleIntoAislesLists(...)`
    - `patchPromoteOperationalJobInAisleJobs(...)`
- `frontend/src/hooks/useMutations.ts`
  - mutation hooks and wiring only
  - delegates specialized patch/invalidation decisions to helper modules

## Conventions expected going forward

1. **No hardcoded key roots**: use `queryKeys` factories for all invalidation/patch selectors.
2. **Conservative patching only**: patch fields known from mutation input/response; avoid invented aggregates.
3. **No-op aware patches**: unchanged transforms must return original references so invalidation fallback remains active.
4. **Fallback-first safety**: if cache is missing or unpatchable, invalidate the narrowest relevant prefix.
5. **Domain-local helpers**: keep review-specific and non-review mutation helpers separate unless semantics truly converge.
6. **Document subtle behavior**: add short comments where patch-vs-invalidate decisions are non-obvious.

## Why this is maintainable now

- Review strategy logic lives in one orchestration function instead of duplicated branches in hooks.
- Non-review mutation patch helpers are colocated and explicit.
- Hook file remains readable (wiring), while patch details stay near their domain logic.

## Deferred debt (intentionally)

- No generic mutation framework across all domains.
- No global entity normalization store.
- No broad optimistic updates.
- No client-side recomputation of merge/analytics aggregates.

These stay deferred to keep behavior auditable and avoid over-abstraction.
