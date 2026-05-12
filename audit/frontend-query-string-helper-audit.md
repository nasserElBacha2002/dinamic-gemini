# Frontend query-string helper audit and P1/P2 implementation

## Executive summary

**Status:** `FRONTEND_QUERY_HELPER_P4_1_IMPLEMENTED`

P1–P3.2 as before; **P4.1** migrates `buildReviewQueueQueryString` to `buildQueryString` with golden tests (`tests/api/reviewQueueApi.test.ts`). `min_confidence` / `max_confidence` use **string** wire values when defined and not NaN (with `{ trim: false }`) to preserve legacy `String(Infinity)` etc., which numeric-only serialization would drop. `queryParamCanonicalization.ts` unchanged. Focused tests including review queue: **38** pass. Full `npm run test -- --run`: **575 passed**, **4 failed** in `CreateAisleDialog.test.tsx` only (unrelated).

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
| `frontend/src/api/reviewQueueApi.ts` | `buildReviewQueueQueryString`, `getPositionDetail` | P4.1: list query via `buildQueryString` + `transform` for `traceability` / `position_status`; confidence as string wire when not NaN; P3.2: `getPositionDetail` |

---

## Deferred files

| File | Reason deferred |
|------|-----------------|
| `jobsApi.ts` | `buildAislePositionsQueryString` + `consolidate_by_sku` false-only — **P4.2** |
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
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts tests/api/reviewQueueApi.test.ts` | Pass (**38** tests) |
| `npm run test -- --run` (full suite) | **575 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |
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
| `reviewQueueApi.ts` | `buildReviewQueueQueryString` — **migrated in P4.1** |
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

## P4.1 Review queue parity migration

### Current behavior captured

| Case | Expected output |
|------|-----------------|
| `q` undefined | `''` |
| Only blank strings (`inventory_id`, `aisle_id`, `sku_contains` spaces/empty) | `''` |
| `inventory_id` trimmed | `?inventory_id=inv-1` |
| `traceability` / `position_status` | Trimmed, then **lowercase** (`?traceability=pending`) |
| `has_evidence` / `qty_zero` | `true` / `false` emitted only for strict boolean; `null` / `undefined` omitted |
| `page` / `page_size` | Omitted when `< 1` |
| `min_confidence` / `max_confidence` | Omitted when `null`/`undefined` or **NaN**; otherwise `String(value)` (including `Infinity`) |
| `sort_by` / `sort_dir` | Trimmed; blank omitted |
| Multi-field | Param order: `inventory_id`, `aisle_id`, `min_confidence`, `max_confidence`, `traceability`, `has_evidence`, `qty_zero`, `sku_contains`, `position_status`, `sort_by`, `sort_dir`, `page`, `page_size` |

### Migrated

| File | Function | Notes |
|------|----------|-------|
| `frontend/src/api/reviewQueueApi.ts` | `buildReviewQueueQueryString` | `buildQueryString` entry list preserves legacy order; confidence wired as **strings** when `!= null && !Number.isNaN` + `{ trim: false }` for parity with non-finite numeric `String` |

### Canonicalization alignment

`canonicalizeReviewQueueListQuery` was **re-read**; omission rules (trim, lowercase on traceability/position_status, strict booleans, positive ints for page) match the wire builder. **No edits** to `queryParamCanonicalization.ts`.

### Tests added

`frontend/tests/api/reviewQueueApi.test.ts`: undefined/empty query; blank strings omitted; trimmed `inventory_id`; lowercase `traceability` / `position_status`; boolean true/false pair; null booleans omitted; pagination `page` 0 dropped; combined order; NaN confidence omitted; `Infinity` confidence string preserved.

### Deferred

| File | Reason |
|------|--------|
| `jobsApi.ts` | Deferred to **P4.2** — aisle positions query + `consolidate_by_sku` false-only and extra branches. |

### Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts tests/api/reviewQueueApi.test.ts` | Pass (**38** tests) |
| `npm run build` | Pass |
| `npm run test -- --run` (full suite) | **575 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |

### Status

`FRONTEND_QUERY_HELPER_P4_1_IMPLEMENTED`

---

## Final recommendation

Migrate **`buildAislePositionsQueryString`** in **P4.2** with parity tests (`consolidate_by_sku` false-only, `needs_review`, etc.). Observability and capture-sessions remain deferred until explicit truthy / pagination parity is specified.

---

## Final status tag

`FRONTEND_QUERY_HELPER_P4_1_IMPLEMENTED`
