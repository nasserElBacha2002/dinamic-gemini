# Sprint 1.4 — Filters, sorting, search, and real pagination (audit)

## 1. Sprint goal

Establish explicit, screen-oriented **query contracts** and **paginated list responses** for data-heavy v3 surfaces so the next UI iteration can rely on server semantics (no client-side fake pagination over unknown totals). Document honest limits (especially **SKU consolidation** vs **raw fetch cap** for aisle results).

## 2. Target surfaces and required query behavior

| Surface | Search | Filters | Sort | Pagination | Notes |
|--------|--------|---------|------|------------|--------|
| **Inventories** | Name substring (case-insensitive) | Status (exact wire value) | name, timestamps, status, aggregates | `page`, `page_size` (max 200) | Aggregates computed per candidate row after name/status filter; sort on aggregate fields is in-memory over that set. |
| **Aisles** (per inventory) | Code substring | Status | code, status, rollups | Same | Rollups computed for filtered aisles after search/status filter. |
| **Aisle results** (positions) | SKU filter (existing, raw/product join) | status, needs_review, min_confidence | Post-consolidation: created_at, updated_at, confidence, sku, quantity | Post-consolidation page | Raw rows capped by `V3_POSITIONS_AISLE_RAW_CAP` (default 2000); `raw_fetch_truncated` signals incomplete totals. |
| **Review queue** | **Not implemented** (no SKU/name search param) | inventory_id, aisle_id, min_confidence | updated_at, created_at, confidence | Same | Filter/sort/pagination only; free-text search is a documented gap vs the original cross-surface “search” goal. |
| **Metrics tables** | — | — | — | — | **Deferred**: metrics remain **cards** via `GET .../metrics`; no new paginated metrics table endpoint in this sprint. |

## 3. Current backend readiness (post–Sprint 1.4)

- **Inventories**: `GET /api/v3/inventories` returns `PaginatedInventoryListResponse` with query params `search`, `status`, `sort_by`, `sort_dir`, `page`, `page_size`.
- **Aisles**: `GET .../inventories/{id}/aisles` returns `PaginatedAisleListResponse` with the same style of params (aisle `search` on code).
- **Aisle results**: `GET .../positions` returns `PositionListResponse` with `page`, `page_size`, `total_items`, `total_pages`, `raw_fetch_truncated`, plus `sort_by` / `sort_dir` (post-consolidation).
- **Review queue**: `GET /api/v3/review-queue/positions` (separate router, same admin auth as v3 inventories).
- **Metrics tables**: unchanged; documented as deferred.

## 4. Current frontend readiness (post–Sprint 1.4)

- `getInventories` / `getAisles` consume paginated DTOs; hooks default to `page=1`, `page_size=200` for list screens until the UI adds controls.
- `useAislePositions` accepts optional `listQuery`; `useResultSummaries` defaults to `page_size=500` so KPI/filter behavior stays useful until server-side KPIs or explicit multi-page UX exist.
- `getReviewQueuePositions` + types available for the future review-queue screen.

## 5. Gap matrix

| Surface | Gap | Severity | Impact | Recommended fix | Now / later |
|--------|-----|----------|--------|-----------------|-------------|
| Inventories | No SQL-side filter/sort for large catalogs | Medium | Memory use grows with inventory count | Add repository-level filtered queries + COUNT | Later |
| Aisle results | Totals incomplete when raw cap hit | Medium | Operators must trust `raw_fetch_truncated` | Raise cap via config; optional true COUNT SQL | Later |
| Aisle results / Results UI | KPIs from one loaded page only | Medium | Misleading if `page_size` &lt; total | Dedicated summary endpoint or fetch all pages | Later |
| Review queue | No free-text search | Medium | Queue screen cannot search SKU/name via API yet | Add `search` query + repo support | Later |
| Review queue | O(aisles) batch read | Medium | Scale limits on huge tenants | Dedicated SQL list with JOIN | Later |
| Metrics | No metrics **table** API | Low | Cards only | New endpoint when product defines rows | Later |

## 6. Query model strategy

- **Shared naming**: `search`, `status`, `sort_by`, `sort_dir`, `page`, `page_size` on list routes where applicable.
- **Response shape**: flat JSON with `page`, `page_size`, `total_items`, `total_pages` plus `items` or `positions`. Shared fields come from the `PageMeta` base model in `listing_schemas.py` (subclassed by inventory/aisle/review-queue list responses and by `PositionListResponse`).
- **No generic framework**: per-route FastAPI `Query` parameters + small dataclasses (`InventoryTableQuery`, `AisleTableQuery`, `ReviewQueueQuery`, `PositionListQuery` for raw repo reads).

## 7. Sprint 1.4 implementation scope (what was implemented)

- Paginated inventories and aisles list APIs + use case filtering/sorting/paging (breaking: object body, not array).
- Positions list: post-consolidation sort/page + metadata + `raw_fetch_truncated` + config `v3_positions_aisle_raw_cap`.
- Review queue list: filters, sort, pagination, **no** SKU/name search.
- Tests: use-case tests; HTTP route tests in `test_sprint_1_4_list_routes.py`; legacy wiring tests updated for `{ items }` payloads.
- **Not in scope / deferred:** metrics tables API; review-queue free-text search.

## 8. Files touched (reference)

**Backend**: `contracts.py`, `repositories.py` (position `list_by_aisle` sort args), `listing_schemas.py`, `position_schemas.py`, `review_queue_schemas.py`, `inventories.py`, `aisles.py`, `positions.py`, `review_queue.py`, `server.py`, `dependencies.py`, `config.py`, `list_inventory_list_items.py`, `list_aisles_with_status.py`, `list_aisle_positions.py`, `list_review_queue.py`, SQL/memory position repositories, tests under `backend/tests/...`.

**Frontend**: `client.ts`, `responses.ts`, `useInventories.ts`, `useAisles.ts`, `usePositions.ts`, `useResultSummaries.ts`, `InventoriesList.tsx`, `InventoryDetail.tsx`.

---

## Deliverables summary

1. **Audit**: this document (sections 1–8).
2. **Implemented**: paginated inventories/aisles; positions post-consolidation pagination/sort + truncation flag; review-queue route; config for raw cap; frontend alignment + defaults.
3. **Tests**: updated/added use case tests; API wiring tests adjusted for `{ items }` payloads; `test_list_review_queue.py`.
4. **Fully ready (for this sprint’s definition):** inventories list, aisles list, aisle results list (with truncation semantics), review queue list **with filters/sort/pagination only**.
5. **Partially ready:** the original five-surface “search everywhere” goal is **not** met for review queue (no search param). Results overview KPIs still derived from a single requested page (default 500).
6. **Not delivered in 1.4:** metrics **tables** API (metrics cards unchanged). SQL scale optimizations.
7. **Risks**: reliance on in-memory sort/filter for inventory/aisle aggregates at scale; raw cap on positions.
8. **Next sprint suggestion**: UI pagination controls wired to query params; optional `GET .../positions/summary` or metrics for KPIs; SQL COUNT + filter paths for inventories/aisles; review-queue SQL path; **review-queue search** if product confirms.

---

## 9. Sprint 1.4 closure (honest status)

**Safe to close Sprint 1.4 as a “listing foundation” sprint** if scope is read as: paginated list contracts, query params on the four implemented surfaces, and explicit documentation of limits — **not** as full completion of every row in the original five-surface vision.

| Original surface | Delivered in 1.4? |
|------------------|-------------------|
| 1. Inventories | **Yes** — search, filter, sort, pagination + breaking paginated JSON body. |
| 2. Aisles | **Yes** — same. |
| 3. Aisle results | **Yes** — with **`raw_fetch_truncated`**: `total_items` / `total_pages` may be window-local, not aisle-global. |
| 4. Review queue | **Partial** — filters, sort, pagination; **no** free-text search. |
| 5. Metrics tables | **No** — explicitly deferred; metrics **cards** only. |

## 10. Breaking contract changes (documented)

- **`GET /api/v3/inventories`**: response body is `{ items, page, page_size, total_items, total_pages }`, not a JSON array.
- **`GET /api/v3/inventories/{inventory_id}/aisles`**: same.

OpenAPI, route docstrings, frontend `client.ts` / `responses.ts`, and this doc state this explicitly.

## 11. Aisle results truncation (consumer rule)

When **`raw_fetch_truncated === true`**:

- Treat **`total_items`** and **`total_pages`** as counting **only** consolidated rows produced from the **raw rows that were loaded** (capped by `V3_POSITIONS_AISLE_RAW_CAP`).
- Do **not** use them as authoritative “full aisle” totals; show UX that totals may be incomplete or disable misleading pager affordances until a future true-count or higher cap strategy exists.

## 12. `PageMeta` in code

`PageMeta` in `listing_schemas.py` is the shared base for pagination fields. `PaginatedInventoryListResponse`, `PaginatedAisleListResponse`, `PositionListResponse` (via inheritance), and `ReviewQueueListResponse` reuse it so descriptions and structure stay aligned without a separate framework.
