# Frontend Phase 8 — Cache / mutation observability (dev)

## Purpose

After Phases 0–7, cache behavior (canonical keys, narrowed invalidation, strategies, patching, fallbacks) is **correct by design** but hard to **verify in runtime**. Phase 8 adds a **small, optional observability layer** so developers can:

- See whether review actions used **patch hits** vs **fallback invalidations** vs **direct** invalidations (e.g. merge after aisle results).
- See **non-review** patch outcomes (`create_aisle`, `promote_operational_job`).
- See **mutation-level invalidation labels** for high-traffic hooks (`useCreateAisle`, `useStartAisleProcessing`, `useCancelAisleJob`, `useRetryAisleJob`, `useRunAisleMerge`, `usePromoteAisleOperationalJob`).
- See **explicit `fetchQuery`** refresh for merge-results (single driver vs duplicate invalidate+refetch).

This is **not** product analytics, not a telemetry vendor, and not a guarantee of network-level tracing.

## When it runs

| Environment | Default |
|-------------|---------|
| Vite **development** (`import.meta.env.DEV`) | **On** (events recorded; optional `console.debug`) |
| Vitest (`import.meta.env.MODE === 'test'`) | **Off** unless tests call `setCacheMutationObservabilityTestOverride(true)` |
| Production build | **Off** unless `localStorage.setItem('dinamic:cacheObs', '1')` |

Disable console noise in dev (keep ring buffer + `window` API):

```js
localStorage.setItem('dinamic:cacheObs:console', '0')
```

Force on in a production-like build (e.g. staging repro):

```js
localStorage.setItem('dinamic:cacheObs', '1')
```

## Developer API

### In-browser (`window`)

When the first event is recorded while observability is active, the module attaches:

```ts
window.__DINAMIC_CACHE_OBS__ = {
  getRecent(): Array<CacheMutationObservabilityEvent & { at: number }>,
  clear(): void,
  isActive(): boolean,
}
```

Example DevTools session after a review + merge + promote:

```js
window.__DINAMIC_CACHE_OBS__?.getRecent().slice(-10)
window.__DINAMIC_CACHE_OBS__?.clear()
```

### Programmatic (tests only)

- `setCacheMutationObservabilityTestOverride(true | false | null)` — `null` restores normal rules.
- `getCacheMutationObservabilityEvents()` — snapshot of the ring buffer (max 80 events).
- `clearCacheMutationObservabilityEvents()`

## Event kinds

### `review_action_cache`

Emitted from `applySubmitReviewActionCacheEffects` (`reviewActionCachePatch.ts`).

- **`strategy`**: `reviewQueue` | `aisleResults` | `detail` | `default`
- **`patchHits`**: domains updated via `setQueryData` / `removeQueries` without needing invalidation for that domain (`review_queue_list`, `position_detail`, `positions_list`).
- **`fallbackInvalidations`**: labels for `invalidateQueries` used because patch missed, cache absent, or delete path.
- **`directInvalidations`**: intentional follow-ups not framed as “patch failed” — today **`mergeResults`** after `aisleResults` only.

**Reading signals**

- Many **`patchHits`** and empty **`fallbackInvalidations`** → patching is doing its job for that action.
- Empty **`patchHits`** and long **`fallbackInvalidations`** → cache was cold or row missing; expect more refetch traffic.
- **`default` strategy** → no `strategy` passed; expect broad **`directInvalidations`** list (Phase 3 compatibility).

### `non_review_patch`

Emitted from `mutationCachePatch.ts` after `patchCreateAisleIntoAislesLists` / `patchPromoteOperationalJobInAisleJobs`.

- **`patched`**: `true` if local list was updated.
- **`note`**: short reason string for skipped paths.

### `mutation_invalidations`

Emitted from `useMutations.ts` after success for:

- `useCreateAisle`
- `useStartAisleProcessing` / `useCancelAisleJob` / `useRetryAisleJob` (labels match each hook’s `invalidateQueries` set)
- `useRunAisleMerge`
- `usePromoteAisleOperationalJob`

- **`labels`**: human-readable domain list aligned with `queryKeys.inventories.*` factory names (dotted paths such as `inventories.positions`, `inventories.aisleJobs`), not raw query keys — to estimate fan-out and compare across flows.

### `explicit_refresh`

Emitted from `AislePositionsPage` after merge success **`fetchQuery`** for merge-results.

- **`keySummary`**: truncated query key string from `summarizeQueryKey`.
- Confirms the **single** explicit refresh path for merge-results (vs duplicate invalidate + refetch).

## What this does **not** guarantee

- No per-HTTP-request counters (would need global `queryCache` subscription or fetch wrapper).
- No automatic detection of “double GET” beyond what you infer from events + Network tab.
- No persistence across full page reloads (in-memory ring buffer only).
- No PII scrubbing beyond using ids already in query keys (keep DevTools sessions internal).

## Instrumented flows (minimum set)

1. Review action (queue / aisle / detail / default) — `review_action_cache`
2. Merge — `mutation_invalidations` (`inventories.positions`) + `explicit_refresh` (`merge_merge_results`)
3. Promote — `non_review_patch` + `mutation_invalidations`
4. Create aisle — `non_review_patch` + `mutation_invalidations`
5. Start aisle processing — `mutation_invalidations`

## Phase 9 (guardrails)

After instrumenting, use **Phase 9** for static checks and dev warnings: [`frontend-phase9-cache-guardrails.md`](./frontend-phase9-cache-guardrails.md).

## Related code

- `frontend/src/dev/cacheMutationObservability.ts` — ring buffer, toggles, record helpers, `window` hook.
- `frontend/src/dev/cacheMutationGuardrails.ts` — dev warnings driven from observability events.
- `frontend/src/hooks/reviewActionCachePatch.ts` — review strategy outcomes.
- `frontend/src/hooks/mutationCachePatch.ts` — Phase 6 patch outcomes.
- `frontend/src/hooks/useMutations.ts` — mutation invalidation summaries.
- `frontend/src/pages/AislePositionsPage.tsx` — merge `fetchQuery` marker.

## Tests

`frontend/tests/cacheMutationObservability.test.ts` covers:

- Inactive-by-default under Vitest without override.
- Recording of `explicit_refresh` + `mutation_invalidations`.
- `summarizeQueryKey` shape.
- `applySubmitReviewActionCacheEffects` emits `review_action_cache` with expected `patchHits` for a seeded `reviewQueue` scenario.
