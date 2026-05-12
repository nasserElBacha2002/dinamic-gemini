# Frontend query-string helper audit and P1/P2 implementation

## Executive summary

**Status:** `FRONTEND_QUERY_HELPER_P5_CLOSED_WITH_OBSERVATIONS`

P1–P4.2 complete; **P5** decision pass: migrated **observability** metrics query and **capture-sessions** list query to `buildQueryString` with documented parity (`trim: false` on observability for legacy truthy semantics; capture `page`/`page_size` use `{ min: 1 }` ≡ legacy `> 0` for integer pages). **adminAi** composed-prompt query stays manual (required keys). **aislesApi** / **analyticsApi** download/merge `URLSearchParams` remain manual (see § P5). `queryParamCanonicalization.ts` unchanged. Targeted helper + canonicalization + observability + capture tests: **36** in that bundle; full suite **593 passed**, **4 failed** (`CreateAisleDialog.test.tsx`, unrelated).

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
| `frontend/src/api/jobsApi.ts` | `buildAislePositionsQueryString`, `listAisleJobs` | P4.2: aisle positions list + optional `limit` on aisle jobs list |
| `frontend/src/api/observabilityApi.ts` | `buildObservabilityMetricsQueryString`, `getObservabilityMetrics` | P5: optional filters; **`trim: false`** preserves legacy truthy / whitespace wire behavior |
| `frontend/src/features/ingestionSessions/api/captureSessionsApi.ts` | `buildCaptureSessionsQuery`, `getCaptureSessions` | P5: list filters; `{ min: 1 }` for `page` / `page_size` (integer parity with `> 0`) |

---

## Deferred files

| Note |
|------|
| No optional list-query modules remain deferred for migration; non-migrated `URLSearchParams` usages are classified in **§ P5** (manual by design). |

---

## Canonicalization alignment

`frontend/src/api/queryParamCanonicalization.ts` was **inspected and left unchanged**. Inventories list wire builder comment references staying aligned with `canonicalizeInventoriesListQuery` omission rules. No new dependency from canonicalizers → `buildQueryString` in this phase.

---

## Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts tests/observabilityMetricsApi.test.ts tests/api/captureSessionsApi.test.ts` | Pass (**36** tests in this bundle) |
| `npm run test -- --run` (full suite) | **593 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |
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
| `jobsApi.ts` | `buildAislePositionsQueryString` — **migrated in P4.2** |
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
| `jobsApi.ts` | Migrated in **P4.2** — see § P4.2. |

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

## P4.2 Jobs API / aisle positions parity migration

### Current behavior captured

| Case | Expected output |
|------|-----------------|
| `q` undefined | `''` |
| `{}` (no fields) | `''` |
| Blank `status` / `sku_filter` | omitted |
| `status` / `sku_filter` | Trimmed; **no** lowercasing on `status` |
| `needs_review` | Both `true` and `false` when non-null; `null` omitted |
| `min_confidence` | Omitted when `null`/`undefined` or **NaN**; else `String(value)` (including `Infinity`) |
| `page` / `page_size` | Omitted when `< 1` |
| `sort_by` / `sort_dir` / `job_id` | Trimmed non-empty |
| `consolidate_by_sku` | Only `?consolidate_by_sku=false` when exactly `false` |
| Multi-field order | `status`, `needs_review`, `min_confidence`, `sku_filter`, `page`, `page_size`, `sort_by`, `sort_dir`, `job_id`, `consolidate_by_sku` |
| `listAisleJobs` `limit` | `?limit=N` only when `limit >= 1`; else no query |

### Migrated

| File | Function | Notes |
|------|----------|-------|
| `frontend/src/api/jobsApi.ts` | `buildAislePositionsQueryString` | Exported; `consolidate_by_sku` via `{ emit: 'false-only' }`; `min_confidence` string wire + `{ trim: false }` |
| `frontend/src/api/jobsApi.ts` | `listAisleJobs` | `buildQueryString([['limit', options?.limit, { min: 1 }]])`; path uses returned `?…` or empty |

### Left manual / deferred

| Function / area | Reason |
|-----------------|--------|
| Merge / merge-results URL builders | None in `jobsApi.ts` (aisles API owns merge paths). |

### Canonicalization alignment

`canonicalizeAislePositionsListQuery` was **re-read**; omission rules match wire (`needs_review` when non-null, `consolidate_by_sku` only `false`, positive pagination, trimmed text). Canonicalizer still uses `normalizeFiniteConfidence` for cache keys (drops `Infinity` on wire that is rare); **no** change to `queryParamCanonicalization.ts`.

### Tests added

`frontend/tests/api/jobsApi.test.ts` (11): undefined/empty; blank filters; trim / no lowercasing on status; pagination; `needs_review` true/false; `consolidate_by_sku` false-only; `min_confidence` NaN/finite/Infinity; combined param order.

### Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts tests/api/reviewQueueApi.test.ts tests/api/jobsApi.test.ts` | Pass (**49** tests) |
| `npm run build` | Pass |
| `npm run test -- --run` (full suite) | **586 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |

### Status

`FRONTEND_QUERY_HELPER_P4_2_IMPLEMENTED`

---

## P5 Deferred builders decision pass

### Remaining usages inspected

| File | Function / area | Decision | Reason |
|------|-----------------|----------|--------|
| `observabilityApi.ts` | Metrics GET query | **MIGRATE** | Optional filters; parity preserved with **`trim: false`** on all string fields (legacy `if (params.from)` truthy semantics, including whitespace-only strings). |
| `captureSessionsApi.ts` | `buildCaptureSessionsQuery` | **MIGRATE** | Optional list filters; `{ min: 1 }` matches legacy `page > 0` / `pageSize > 0` for **integer** pages (non-integer `0 < page < 1` edge differs — documented observation). |
| `adminAiApi.ts` | `getAdminAiComposedPrompt` query | **KEEP_MANUAL** | Required fixed keys; `new URLSearchParams({ … })` is clearer than optional-filter helper. |
| `aislesApi.ts` | merge / merge-results / export CSV query | **KEEP_MANUAL** | Mixed required/conditional keys (`job_id`, `format`, `technical`); small and explicit. |
| `analyticsApi.ts` | benchmark CSV / compare-many query | **KEEP_MANUAL** | Same pattern — explicit `URLSearchParams` for download/compare flows. |

### Migrated in P5

| File | Function | Notes |
|------|----------|-------|
| `frontend/src/api/observabilityApi.ts` | `buildObservabilityMetricsQueryString` | Exported; all params `trim: false`; `getObservabilityMetrics` composes path + query. |
| `frontend/src/features/ingestionSessions/api/captureSessionsApi.ts` | `buildCaptureSessionsQuery` (exported) | `aisle_id`, `status`, `page`, `page_size`; default trim for strings. |

### Kept manual

| File | Function / area | Reason |
|------|-----------------|--------|
| `adminAiApi.ts` | `getAdminAiComposedPrompt` | Required query keys; object constructor is minimal and explicit. |
| `aislesApi.ts` | Merge / export-related query construction | Conditional keys tied to job/run context; not optional-filter lists. |
| `analyticsApi.ts` | CSV / multi-job compare queries | Explicit `URLSearchParams` for fixed download shapes. |

### Deferred

| File | Function / area | Reason |
|------|-----------------|--------|
| *(none)* | — | Remaining `URLSearchParams` in scoped API dirs are either migrated or **KEEP_MANUAL** above. |

### Final frontend query-string convention

Future API work: follow this section as the project norm.

Use **`buildQueryString`** for API-client **optional** query filters when params are independently optional and omission rules match helper capabilities (trim, `min`, `transform`, boolean `emit`).

Keep **`URLSearchParams` manual** when:

- query keys are **required** for the request shape;
- the builder is **not** an optional filter list;
- behavior depends on **multiple fields** or non-standard truthy rules (if migrating, document parity — e.g. observability **`trim: false`**);
- manual code is **clearer** or migration would need one-off helper options.

Do **not** use `buildQueryString` for **path segments**; continue using **`encodeURIComponent`** for dynamic path IDs.

### Tests added / updated

- `tests/observabilityMetricsApi.test.ts`: `buildObservabilityMetricsQueryString` whitespace + empty-string cases.
- `tests/api/captureSessionsApi.test.ts`: capture list query goldens (parsed `URLSearchParams` where encoding differs).

### Validation

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass |
| `npm run test -- --run tests/api/queryString.test.ts tests/queryParamCanonicalization.test.ts tests/observabilityMetricsApi.test.ts tests/api/captureSessionsApi.test.ts` | Pass (**36** tests) |
| `npm run build` | Pass |
| `npm run test -- --run` (full suite) | **593 passed**, **4 failed** (`CreateAisleDialog.test.tsx` only; unrelated) |

### Final status

`FRONTEND_QUERY_HELPER_P5_CLOSED_WITH_OBSERVATIONS`

---

## Final status tag

`FRONTEND_QUERY_HELPER_P5_CLOSED_WITH_OBSERVATIONS`
