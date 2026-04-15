# Frontend Phase 9 — Guardrails, static checks, and regression protection

Phase 8 made cache/mutation behavior **observable**. Phase 9 makes the system **self-protecting** in a lightweight way: static convention checks, dev-only runtime guardrails on observability events, invariant tests, and a short pre-merge checklist.

## 1. System invariants (enforced / documented)

| Area | Rule |
|------|------|
| **Query keys** | Prefer `queryKeys` factories; do not hand-compose the same segments outside `api/queryKeys.ts` (e.g. `'merge-results'`). |
| **Aisles list hook** | Use `queryKeys.inventories.aislesListTable(inventoryId)` — not `queryKey: [...queryKeys.inventories.aisles(inv), params]`. |
| **Invalidate** | `invalidateQueries({ queryKey: ... })` must use `queryKeys` factories, not a literal `queryKey: ['v3', ...]`. |
| **Key / request parity** | List hooks must use the same canonicalization for **key** and **queryFn** inputs (see Phase 2.1). |
| **Merge refresh** | Single driver for merge-results refresh after manual merge (see architecture note: `fetchQuery` on page + positions invalidation in mutation). |
| **Review strategy** | Contextual routes should pass `strategy` from `QuickReviewDrawer`; default strategy implies broad invalidation — guardrail warns in dev. |
| **Patching** | No invented server state; no-op patches must not suppress needed fallbacks (Phase 5 — covered by existing tests + observability flags). |

## 2. Automated checks

### Script: `npm run check:cache` (from `frontend/`)

**CI:** `.github/workflows/frontend-validate.yml` runs `npm run check:cache`, `typecheck`, and `test` on pushes/PRs that touch `frontend/**`.

Runs `node scripts/check-cache-conventions.mjs`:

- Fails if any file under `src/` (except `api/queryKeys.ts`) contains **`'merge-results'`** as a string (prevents duplicate key roots outside the factory file). HTTP paths in `client.ts` use `merge-results` inside template literals without quotes — they do not match.
- Fails on **`queryKey: [...queryKeys.inventories.aisles(`** manual spread (use `aislesListTable`).
- Fails on **`invalidateQueries({ queryKey: ['`** literal-root invalidation.

The merge-results scan uses source text with **`//` line comments** and **`/* */` blocks** stripped first, so prose comments are less likely to false-positive.

## 3. Runtime guardrails (development)

Implemented in `frontend/src/dev/cacheMutationGuardrails.ts`, invoked from `cacheMutationObservability.ts` after each recorded event when guardrails are active.

| Control | Behavior |
|---------|----------|
| **Default** | On in Vite **dev**; **off** in Vitest unless `setCacheMutationGuardrailsTestOverride(true)`. |
| **Disable** | `localStorage.setItem('dinamic:cacheGuardrails', '0')`. |
| **Staging / prod build** | Off unless `localStorage.setItem('dinamic:cacheGuardrails', '1')`. |

### Warnings (deduped where noted)

- **`review_action_used_default_strategy`** — review observability used `strategy: 'default'` (broad fan-out); prefer passing strategy from the drawer when context is known.
- **`review_queue_multiple_fallbacks`** — two or more fallback invalidations on `reviewQueue` strategy (cold cache / missing row).
- **`aisle_results_cold_cache_heavy_fallback`** — `aisleResults` with **no** patch hits but ≥2 fallbacks.
- **`mutation_high_invalidation_fanout`** — more than six invalidation labels on one mutation summary.
- **`duplicate_explicit_refresh_same_key`** — two `explicit_refresh` events for the same flow/key summary within 2s (possible duplicate refresh drivers).

Warnings use `console.warn('[dinamic:cache-guard]', …)` with session-level dedupe keys to limit noise.

## 4. Tests

- `frontend/tests/cacheSystemInvariants.test.ts` — canonical key parts, merge key factory shape, `computeGuardrailNotices` outcomes.
- Existing cache/review tests continue to protect patch/fallback semantics.

## 5. Pre-merge checklist

See **[`frontend-cache-data-pre-merge-checklist.md`](./frontend-cache-data-pre-merge-checklist.md)**.

## 6. What Phase 9 does **not** do

- No custom ESLint plugin or new mandatory devDependencies.
- No global HTTP tracing or per-request automatic counters.
- No blocking of production builds unless CI wires `check:cache` (recommended but optional).

## Related docs

- Phase 8: [`frontend-phase8-cache-observability.md`](./frontend-phase8-cache-observability.md)
- Architecture overview: [`frontend-cache-update-architecture-phase0-7.md`](./frontend-cache-update-architecture-phase0-7.md) (includes Phase 9 pointer)
