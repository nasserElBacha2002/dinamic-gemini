# Sprint 1.4 — Aisle Results and Review-Entry Readiness Audit

## 1. Sprint goal

Make the **per-aisle results list** (Aisle Results / review entry) **contract- and filter-ready** for the v3.3 direction: operators can scan rows for SKU, quantity provenance, review need, traceability, evidence, and confidence **without inferring domain rules in the client**, and the API can support **server-side filters and paging** for large aisles before deeper review-workflow work.

## 2. Target results-table requirements

From `Plan implementacion 3.3.md` / `Re diseño 3.3.md` (§4.1 Aisle Results, §9.7):

| Need | Contract / behavior |
|------|---------------------|
| Stable row identity + navigation to detail | `id` (position / representative after consolidation), `aisle_id` |
| SKU / product line | `sku` (from summary + product projection) |
| Quantity for display | `qty`, `qtySource`, `qtyResolved`, `detected_quantity`, `corrected_quantity` |
| Review state | `status`, `needs_review` (+ frontend `ResultSummary.reviewStatus` mapping) |
| Traceability / quality | `traceability_status`, `has_evidence` |
| Confidence | `confidence` |
| Filters / sort (product direction) | **Stable query params** on `GET .../positions` matching §9.7 |
| “Qty zero” operational meaning | **Display quantity** zero (resolved / corrected), not raw detected only |

**Semantics note:** `ListAislePositionsUseCase` still **consolidates** by canonical SKU after the repository returns a page of raw positions. Pagination and filters apply **before** consolidation; row counts may differ from post-merge rows. Documented as a known tradeoff until a dedicated “aggregated results” API is justified.

## 3. Current backend readiness (pre–Sprint 1.4)

**Strong**

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` → `PositionListResponse` with `PositionSummaryResponse` rows: quantity contract (v3.2.2), `has_evidence`, `traceability_status`, `sku`, etc.
- `position_to_summary` centralizes mapping; list and detail stay aligned.
- `ListAislePositionsUseCase` accepts `PositionListQuery` and performs SKU consolidation.

**Weak**

- Route did **not** expose `PositionListQuery` query parameters (filters/pagination only usable if callers constructed the command in-process).
- Use case had two repository paths (`list_by_aisle` vs `list_by_aisle_query`); defaults were equivalent but duplicated.

## 4. Current frontend readiness (pre–Sprint 1.4)

- **Result-centric** layer (`features/results`): `mapPositionSummaryToResultSummary`, KPIs, quick filters, table — generally solid.
- **Gap:** “Qty zero” quick filter and KPI used **`detectedQty === 0` only**, ignoring operator-facing **resolved** quantity (`resolvedQty` / corrections).

## 5. Gap matrix

| Area | Gap | Severity | Impact | Recommended fix | implement now / later |
|------|-----|----------|--------|-----------------|----------------------|
| API | No query params on list positions | High | Cannot drive server-side filter/sort/pagination from UI or tools | Expose §9.7 params on `GET .../positions` | **Now** |
| Use case | Dual repo branches | Low | Confusion / drift risk | Always use `list_by_aisle_query` with default `PositionListQuery()` | **Now** |
| Frontend qty zero | KPI/filter ignore resolved qty | Medium | Wrong “qty zero” cohort | Use `resolvedQty ?? detectedQty === 0` | **Now** |
| Consolidation vs pagination | Page is pre-merge | Medium | Page size ≠ merged row count | Document; optional future aggregated list API | **Later** |
| Row `display_status` | No single enum beyond status+needs_review | Low | UI maps in mapper | Keep mapper; optional `display_review_status` field later | **Later** |

## 6. Proposed Sprint 1.4 scope (implemented)

1. **API:** Optional query parameters on `GET .../positions`: `status`, `needs_review`, `min_confidence`, `sku_filter`, `page`, `page_size` (max 500), wired to `PositionListQuery`.
2. **Use case:** Single path: `list_by_aisle_query` with `command.query or PositionListQuery()`.
3. **Schema:** Clarify `PositionSummaryResponse` as the Aisle Results row shape.
4. **Frontend client:** `getAislePositions(id, aisleId, listQuery?)` + `AislePositionsListQuery` type.
5. **Frontend selectors:** `qty_zero` KPI and filter use resolved display quantity.

## 7. Files modified

- `backend/src/application/use_cases/list_aisle_positions.py`
- `backend/src/api/routes/v3/positions.py`
- `backend/src/api/schemas/position_schemas.py`
- `backend/tests/application/use_cases/test_list_aisle_positions_query.py`
- `frontend/src/api/client.ts`
- `frontend/src/features/results/selectors/resultsFilters.ts`
- `frontend/src/features/results/selectors/resultsKpi.ts`
- `frontend/tests/resultsOverviewSelectors.test.ts`
- `docs/Sprint14_aisle_results_readiness.md`

---

## Verification

**Backend**

```bash
cd backend && .venv/bin/python -m pytest tests/application/use_cases/test_list_aisle_positions_query.py tests/api/test_positions_deduplication_v3_2_3.py -q
```

**Frontend**

```bash
cd frontend && npx vitest run tests/resultsOverviewSelectors.test.ts
```

---

## Remaining gaps (not in 1.4)

- **Total count / total pages** for merged rows (would need COUNT strategy or post-merge pagination).
- **Global Review Queue** and cross-aisle summaries (Sprint 1.x / product phase).
- **Explicit `display_review_status` in API** if product wants one string without client mapping.

## Recommended next sprint (after 1.4)

**Sprint 1.5 — Agregados y métricas** (per plan): dashboard/inventory-level KPIs and analytics contracts, building on list + detail readiness.
