# Frontend query-string helper audit and P1/P2 implementation

## Executive summary

**Status:** `FRONTEND_QUERY_HELPER_READY_WITH_OBSERVATIONS`

P1 (`buildQueryString` in `frontend/src/api/queryString.ts` + unit tests) and P2 (migrated list builders in **clients**, **analytics**, **inventories**, **aisles** API modules) are **implemented**. `queryParamCanonicalization.ts` was **not** modified. Full `npm run test` reports **4 failing** tests in `CreateAisleDialog.test.tsx` (pre-existing / unrelated to query-string work); **556** tests pass including **8** new `buildQueryString` tests.

---

## Original read-only audit summary

Repeated pattern across API modules: `new URLSearchParams` → conditional `params.set` with trim / min pagination → `s ? \`?${s}\` : ''`. Higher-complexity builders (review queue booleans + lowercase, jobs aisle positions + `consolidate_by_sku`, suppliers, observability truthy checks, admin AI required keys, capture sessions `page > 0`) were flagged for **later** phases.

---

## Helper design

| Export | Role |
|--------|------|
| `QueryParamValue` | `string \| number \| boolean \| null \| undefined` |
| `QueryParamOptions` | `{ min?: number; trim?: boolean }` (default trim for strings) |
| `QueryParamEntry` | `readonly [key, value, options?]` |
| `buildQueryString(entries)` | Returns `''` or `'?…'` using `URLSearchParams` only (no path encoding) |

Module doc in `queryString.ts` notes alignment with `queryParamCanonicalization.ts` for list endpoints that share cache key semantics.

---

## Migrated files

| File | Function | Notes |
|------|----------|--------|
| `frontend/src/api/clientsApi.ts` | `buildClientsListQueryString` | `page` / `page_size` with `{ min: 1 }`; `q` optional without early `if (!q)` |
| `frontend/src/api/analyticsApi.ts` | `buildAnalyticsQueryString` | `date_from`, `date_to`, `inventory_id`, `aisle_id` |
| `frontend/src/api/inventoriesApi.ts` | `buildInventoriesListQueryString` | search, status, sort, pagination + canonicalization comment |
| `frontend/src/api/aislesApi.ts` | `buildAislesListQueryString` | same shape as inventories list; merge/export builders **unchanged** |

---

## Deferred files

| File | Reason deferred |
|------|-----------------|
| `reviewQueueApi.ts` | Booleans, `.toLowerCase()`, canonicalizer coupling |
| `jobsApi.ts` | Many fields, `consolidate_by_sku` only-when-false |
| `clientSuppliersApi.ts` | Scope / prompt-config-specific rules |
| `observabilityApi.ts` | Truthy vs trim-empty semantics |
| `adminAiApi.ts` | Required fixed query keys object |
| `captureSessionsApi.ts` | `page > 0` vs `>= 1` needs explicit parity review |

---

## Canonicalization alignment

`frontend/src/api/queryParamCanonicalization.ts` was **inspected and left unchanged**. Inventories list wire builder comment references staying aligned with `canonicalizeInventoriesListQuery` omission rules. No new dependency from canonicalizers → `buildQueryString` in this phase.

---

## Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts` | Pass (19 tests) |
| `npm run test -- --run` (full suite) | **556 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only) |
| `npm run build` | Pass |

---

## Final recommendation

Proceed with **P3** (e.g. `clientSuppliersApi` list + prompt query) and **P4** (`reviewQueueApi`, `jobsApi`) only after adding **options** for lowercase / conditional booleans / special numeric rules, with parity tests against current URLs or golden vectors.

---

## Final status tag

`FRONTEND_QUERY_HELPER_READY_WITH_OBSERVATIONS`
