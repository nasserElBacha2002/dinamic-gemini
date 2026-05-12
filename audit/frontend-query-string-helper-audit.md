# Frontend query-string helper audit and P1/P2 implementation

## Executive summary

**Status:** `FRONTEND_QUERY_HELPER_P3_1_IMPLEMENTED`

P1 (`buildQueryString` in `frontend/src/api/queryString.ts` + unit tests), P2 (migrated list builders in **clients**, **analytics**, **inventories**, **aisles** API modules), and **P3.1** (`clientSuppliersApi.ts` simple builders + active-config URL suffix parity) are **implemented**. `queryParamCanonicalization.ts` was **not** modified. Focused helper/canonicalization tests: **20** pass (9 `buildQueryString` tests). Full `npm run test -- --run`: **557 passed**, **4 failed** in `CreateAisleDialog.test.tsx` only (unchanged / unrelated to query-string work).

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
| `frontend/src/api/clientSuppliersApi.ts` | `buildClientSuppliersListQueryString`, `buildSupplierPromptConfigsQueryString`, `getActiveSupplierPromptConfig` | P3.1: see § P3.1 for scope/active URL notes |

---

## Deferred files

| File | Reason deferred |
|------|-----------------|
| `reviewQueueApi.ts` | Booleans, `.toLowerCase()`, canonicalizer coupling |
| `jobsApi.ts` | Many fields, `consolidate_by_sku` only-when-false |
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
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts` | Pass (**20** tests: 9 `buildQueryString`, 11 canonicalization) |
| `npm run test -- --run` (full suite) | **557 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |
| `npm run build` | Pass |

---

## P3.1 Client suppliers migration

### Migrated

| File | Function | Notes |
|------|----------|-------|
| `frontend/src/api/clientSuppliersApi.ts` | `buildClientSuppliersListQueryString` | `page` / `page_size` with `{ min: 1 }`; optional `q` |
| `frontend/src/api/clientSuppliersApi.ts` | `buildSupplierPromptConfigsQueryString` | `scope=all` only when `q.scope === 'all'`; `provider_name` / `model_name` trimmed via helper |
| `frontend/src/api/clientSuppliersApi.ts` | `getActiveSupplierPromptConfig` | `buildQueryString` + **suffix parity**: when both params omitted, URL keeps trailing bare `?` (same as `?${params.toString()}` on empty `URLSearchParams`) |

### Deferred inside clientSuppliersApi

| Function / area | Reason |
|-----------------|--------|
| *(none)* | All simple query builders in this file were migrated; no higher-risk builders remain here. |

### Behavior notes

- **List query:** unchanged param names; pagination still omitted below 1.
- **Prompt configs list:** `scope` query is emitted **only** for `scope=all` (type allows only `undefined` or `'all'`).
- **Active config:** `provider_name` and `model_name` still trim-and-skip when blank; empty query preserves `.../active?` not `.../active`.

### Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts` | Pass (**20** tests) |
| `npm run build` | Pass |
| `npm run test -- --run` (full suite) | **557 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |

### Status

`FRONTEND_QUERY_HELPER_P3_1_IMPLEMENTED`

---

## Final recommendation

Proceed with **P4** (`reviewQueueApi`, `jobsApi`) only after adding **options** for lowercase / conditional booleans / special numeric rules, with parity tests against current URLs or golden vectors. `clientSuppliersApi` simple builders are done in **P3.1**.

---

## Final status tag

`FRONTEND_QUERY_HELPER_P3_1_IMPLEMENTED`
