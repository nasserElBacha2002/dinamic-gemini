# Sprint 1.2 — Screen readiness and contract audit

Source: `Plan implementacion 3.3.md` (Fase 1 / Sprint 1.2), `Re diseño 3.3.md`, Sprint 1.1 alignment work.

## 1. Sprint goal

Validate that backend/frontend contracts can support target product screens **without** unstable hacks; add **minimum list/summary contract improvements** so the next sprint can build tables and shells on stable DTOs. Full dashboard UI, review-queue UI, analytics UI, and pagination are **out of scope** (Sprint 1.4–1.5 / Phase 2).

## 2. Target screens and required data

| Screen | Required data (contract-level) | Notes |
|--------|-------------------------------|--------|
| **Dashboard** | Global KPIs, “attention” slices, recent activity | Needs **aggregates across inventories** — no single v3 endpoint today; **later** (1.5). |
| **Inventories list** | Per row: name, status, dates, **aisle count**, **pending review count**, **last activity** | Was thin `InventoryResponse`; **addressed in 1.2** via list item DTO. |
| **Inventory detail** | Inventory + aisles with status/jobs + optional metrics | **Largely supported** (aisles list, metrics GET); row-level aisle summaries still composed client-side. |
| **Aisle results** | Positions list + filters + KPIs | **Supported** (existing positions API + frontend selectors). |
| **Review queue** | Cross-inventory positions + filters + links to detail | **Not supported** — needs dedicated query API (**Stage 2**). |
| **Result detail** | Position + evidences + review_actions | **Supported**. |
| **Metrics / analytics** | Per-inventory metrics exist; global/trends | Per-inventory **supported**; global/trends **later** (1.5). |

## 3. Current backend readiness

- **v3 routes**: inventories CRUD, metrics, visual refs; aisles; positions list/detail; reviews.
- **Gaps before 1.2**: `GET /inventories` returned only id, name, status, created_at — **no row aggregates** for list tables.
- **After 1.2**: same route returns **inventory list items** with `aisles_count`, `pending_review_count`, `last_activity_at`, `updated_at`.

## 4. Current frontend readiness

- Types mirrored `Inventory`; hooks call `getInventories()`.
- **After 1.2**: `InventoryListItem` type + `getInventories()` return type updated; list page can bind new fields when UI is built.

## 5. Gap matrix

| Screen | Gap | Severity | Impact | Recommended fix | Implement |
|--------|-----|----------|--------|-----------------|-----------|
| Inventories list | Missing row aggregates | High | N+1 or manual composition | List item DTO + use case | **Now** |
| Dashboard | No global summary API | High | Blocked | Dashboard summary endpoint | Later (1.5) |
| Review queue | No cross-inventory positions | Critical | Blocked | New endpoint + pagination | Later |
| Inventory detail | Aisle table columns partly client-derived | Medium | OK short-term | Richer aisle summary DTO | Later (1.3) |
| Metrics | No trends | Medium | Analytics thin | Time-series / rollups | Later (1.5) |

## 6. Proposed Sprint 1.2 scope (implemented)

- **Backend**: `InventoryListItemResponse` + `ListInventoryListItemsUseCase` (inventory + aisle + position repos); `GET /api/v3/inventories` returns enriched list.
- **Frontend**: `InventoryListItem` in `api/types`, `getInventories()` typing, short `screenContracts` note for list row shape.
- **Docs**: this audit artifact.

## 7. Files touched

- Backend: `application/ports/contracts.py` (`InventoryListItem`), `use_cases/list_inventory_list_items.py`, `api/schemas/inventory_schemas.py`, `api/routes/v3/inventories.py`, `api/routes/v3/shared.py`, `api/dependencies.py`, `tests/application/use_cases/test_list_inventory_list_items.py`
- Frontend: `api/types/responses.ts` (`InventoryListItem`), `api/client.ts`, `types/screenContracts.ts`
