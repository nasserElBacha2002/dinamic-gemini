# Sprint 1.3 — Inventory Detail and Aisle Row Readiness Audit

## 1. Sprint goal

Make the **Inventory Detail** screen and its **aisle table** contract-ready for the v3.3 product direction: one list response should carry enough **screen-oriented** fields (identity, processing/job, operational counts, pending review, freshness) so the frontend does not rely on **N+1 composition** or brittle client-side inference.

## 2. Inventory Detail target requirements

From `Plan implementacion 3.3.md` / `Re diseño 3.3.md` (§9.5, §3.4, aisle table):

**Header / summary**

- Inventory name, status, created date, contextual actions (existing `GET /inventories/{id}` path).

**KPI strip (later sprint)**

- Totals: aisles, processed, pending, errors, pending review results, corrections, review completion — many already derivable from metrics endpoint; not part of 1.3 contract work beyond alignment.

**Aisle table — minimum useful row**

| Need | Contract implication |
|------|----------------------|
| Aisle code / identity | `code`, `id` |
| Aisle lifecycle status | `status` |
| Uploaded assets | **count** (not N+1 asset list fetches) |
| Processing / job | `latest_job` (already present) |
| Results volume | **positions count** |
| Pending human review | **count of positions with `needs_review`** (aligned with inventory list semantics) |
| Freshness | **`last_activity_at`** (max of aisle, job, positions, asset uploads) |
| Navigate to results / review | Existing routes; table only needs clarity of counts and state |

## 3. Current backend readiness (pre–Sprint 1.3)

**Existed**

- `GET /api/v3/inventories/{inventory_id}/aisles` → `AisleResponse[]` with `latest_job` per aisle (`ListAislesWithStatusUseCase` + batch job lookup).
- `GET .../metrics` for inventory-level aggregates.
- `PositionRepository.list_by_aisles` for batch position reads (used elsewhere for metrics-style rollups).

**Partial**

- Asset counts required either `GET .../aisles/{id}/assets` per aisle or inferring from other calls → **N+1** on the client.

**Missing (before 1.3)**

- Per-aisle **assets_count**, **positions_count**, **pending_review_positions_count**, **last_activity_at** on the aisle list payload.

## 4. Current frontend readiness (pre–Sprint 1.3)

- `InventoryDetail` used `useAislesList` + **`useAisleAssetCounts`** (`useQueries` → one `getAisleAssets` per aisle) → **N+1** network pattern.
- Results column did not show position counts; “Created” did not match target “Last updated / activity”.
- Row typing was `Aisle` without list-specific rollups.

## 5. Gap matrix

| Area | Gap | Severity | Impact | Recommended fix | Implement now / later |
|------|-----|----------|--------|-----------------|----------------------|
| Aisle list | No per-aisle asset count in list | High | N+1 asset API calls | Batch rollup in backend + expose `assets_count` | **Now** |
| Aisle list | No position / pending review counts | High | Blind operational table; extra calls to positions per aisle | `positions_count`, `pending_review_positions_count` on list | **Now** |
| Aisle list | No single freshness timestamp | Medium | Wrong column (“created” vs “activity”) | `last_activity_at` (max timestamps) | **Now** |
| Inventory KPIs | Header KPI strip not in aisle list | Medium | Still needs metrics / dedicated summary endpoint | Dashboard / detail KPI contracts | **Later** |
| Screen taxonomy | Wire vs product status labels | Low | Already covered by Sprint 1.1 alignment helpers | UI labels only | **Later** |

## 6. Proposed Sprint 1.3 scope (implemented)

1. **`SourceAssetRepository.summarize_assets_for_aisles`** — one grouped query (SQL) / aggregation (memory) for count + `last_uploaded_at` per aisle.
2. **Extend `ListAislesWithStatusUseCase`** — batch `list_by_aisles`, asset rollups, compute pending review (= `needs_review` true, same idea as inventory list), `last_activity_at`.
3. **Extend `AisleResponse`** with additive fields; **list route** maps full rollup; **create** / **status** responses keep defaults (0 / null).
4. **Frontend** — extend `Aisle` type; **remove `useAisleAssetCounts` from Inventory Detail**; show assets, position count, pending review, last activity.

## 7. Files modified

**Backend**

- `backend/src/application/ports/contracts.py` — `AisleAssetRollup`
- `backend/src/application/ports/repositories.py` — `summarize_assets_for_aisles`
- `backend/src/infrastructure/repositories/sql_source_asset_repository.py` — SQL GROUP BY implementation
- `backend/src/infrastructure/repositories/memory_source_asset_repository.py` — in-memory aggregation
- `backend/src/application/use_cases/list_aisles_with_status.py` — rollups + `last_activity_at`
- `backend/src/api/schemas/aisle_schemas.py` — new optional fields on `AisleResponse`
- `backend/src/api/routes/v3/shared.py` — `aisle_to_response(...)` keyword args
- `backend/src/api/routes/v3/aisles.py` — list mapping
- `backend/src/api/dependencies.py` — inject `PositionRepository`, `SourceAssetRepository`

**Tests**

- `backend/tests/application/use_cases/test_list_aisles_with_status.py`
- `backend/tests/infrastructure/repositories/test_memory_source_asset_repository.py`
- Stubs updated: `test_upload_aisle_assets.py`, `test_v3_job_executor_analysis_context.py`, `test_v3_job_executor_phase5.py`

**Frontend**

- `frontend/src/api/types/responses.ts`
- `frontend/src/pages/InventoryDetail.tsx`

---

## Semantics (short)

- **`pending_review_positions_count`**: number of positions in that aisle with `needs_review == true` (aligned with `ListInventoryListItemsUseCase` inventory-level pending count).
- **`last_activity_at`**: maximum of relevant `created_at` / `updated_at` / asset `uploaded_at` for that aisle (operational freshness, not “last review completed” unless that was the latest event).

## Performance note

- One `list_by_aisles` query, one `summarize_assets_for_aisles` query, plus existing job batch — **O(1) queries in number of aisles**, vs previous frontend **O(n)** asset list calls.
