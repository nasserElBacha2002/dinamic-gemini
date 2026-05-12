# Frontend query-string helper audit and P1/P2 implementation

## Executive summary

**Status:** `FRONTEND_QUERY_HELPER_P3_2_IMPLEMENTED`

P1–P3.1 as before; **P3.2** adds `transform` and `emit` on `buildQueryString`, unit tests, and a **small** migration: `getPositionDetail` in `reviewQueueApi.ts`. `queryParamCanonicalization.ts` unchanged. Focused helper/canonicalization tests: **27** pass (16 `buildQueryString`). Full `npm run test -- --run`: **564 passed**, **4 failed** in `CreateAisleDialog.test.tsx` only (unrelated).

---

## Original read-only audit summary

Repeated pattern across API modules: `new URLSearchParams` → conditional `params.set` with trim / min pagination → `s ? \`?${s}\` : ''`. Higher-complexity builders (review queue booleans + lowercase, jobs aisle positions + `consolidate_by_sku`, suppliers, observability truthy checks, admin AI required keys, capture sessions `page > 0`) were flagged for **later** phases.

---

## Helper design

| Export | Role |
|--------|------|
| `QueryParamValue` | `string \| number \| boolean \| null \| undefined` |
| `BooleanEmitMode` | `'always' \| 'true-only' \| 'false-only'` (booleans only) |
| `QueryParamOptions` | `{ min?, trim?, transform?, emit? }` — default string trim; default boolean `emit: 'always'` |
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
| `frontend/src/api/reviewQueueApi.ts` | `getPositionDetail` (query only) | P3.2: `job_id` + `exact_position` via `buildQueryString` with `emit: 'true-only'` for `exact_position` |

---

## Deferred files

| File | Reason deferred |
|------|-----------------|
| `reviewQueueApi.ts` | `buildReviewQueueQueryString` still manual (P4 parity); `getPositionDetail` migrated in P3.2 |
| `jobsApi.ts` | `buildAislePositionsQueryString` + `consolidate_by_sku` false-only; many fields — P4 |
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
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts` | Pass (**27** tests: 16 `buildQueryString`, 11 canonicalization) |
| `npm run test -- --run` (full suite) | **564 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |
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

## P3.2 Helper options design

### Complex patterns reviewed

| File | Pattern | Helper support needed |
|------|---------|------------------------|
| `reviewQueueApi.ts` | `traceability` / `position_status`: trim + `.toLowerCase()` | `transform: (v) => v.toLowerCase()` (P4) |
| `reviewQueueApi.ts` | `has_evidence` / `qty_zero`: emit when `=== true` or `=== false`, skip when null | Default boolean `emit: 'always'` + null skip (P4) |
| `reviewQueueApi.ts` | `exact_position` only when truthy | `emit: 'true-only'` (used in P3.2 for `getPositionDetail`) |
| `jobsApi.ts` | `needs_review` when non-null | `emit: 'always'` (P4) |
| `jobsApi.ts` | `consolidate_by_sku` only when `=== false` | `emit: 'false-only'` (P4) |
| `jobsApi.ts` | `page` / `page_size` with `>= 1` | Existing `{ min: 1 }` (P4) |
| `observabilityApi.ts` | `if (params.from)` etc. (truthy, no trim) | Parity review: differs from trim-to-empty; migrate carefully or keep manual (P4+) |
| `captureSessionsApi.ts` | `page > 0`, `pageSize > 0` | Integer `> 0` matches `{ min: 1 }` for positive pages; still verify edge cases in P4 |

### Helper changes

- **`transform`:** string-only; runs after trim (or raw string when `trim: false`); omit if result is `''`.
- **`emit`:** `'always' \| 'true-only' \| 'false-only'` for **booleans only**; strings and numbers ignore `emit`. Default **`always`** preserves pre–P3.2 behavior.

### Tests added

- Transform after trim (`PENDING` → `pending`).
- Transform returns `''` → omit.
- Two booleans default → `?has_evidence=true&has_conflict=false`.
- `emit: 'true-only'` (only true emitted).
- `emit: 'false-only'` (only false emitted).
- `emit` on string unchanged (`?status=active`).
- `min: 0` allows `page=0` while `min: 1` drops `page_size=0`.

### Migrations performed

| File | Function |
|------|----------|
| `frontend/src/api/reviewQueueApi.ts` | `getPositionDetail` — `job_id` (trim/blank rules via helper) + `exact_position` with `{ emit: 'true-only' }` |

`buildReviewQueueQueryString` was **not** migrated in P3.2.

### Deferred migrations

| File | Reason |
|------|--------|
| `reviewQueueApi.ts` | `buildReviewQueueQueryString` — many branches + canonicalizer coupling; P4 parity |
| `jobsApi.ts` | `buildAislePositionsQueryString` — P4 parity |
| `observabilityApi.ts` | Truthy string semantics vs helper trim |
| `captureSessionsApi.ts` | Explicit `page > 0` parity sign-off |
| `adminAiApi.ts` | Unchanged from prior deferral |

### Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts` | Pass (**27** tests) |
| `npm run build` | Pass |
| `npm run test -- --run` (full suite) | **564 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |

### Status

`FRONTEND_QUERY_HELPER_P3_2_IMPLEMENTED`

---

## Final recommendation

Proceed with **P4**: migrate `buildReviewQueueQueryString` and `buildAislePositionsQueryString` using `transform` + `emit`, with golden parity tests. Observability and capture-sessions builders need explicit truthy/`page > 0` parity before swapping wire serialization.

---

## Final status tag

`FRONTEND_QUERY_HELPER_P3_2_IMPLEMENTED`
