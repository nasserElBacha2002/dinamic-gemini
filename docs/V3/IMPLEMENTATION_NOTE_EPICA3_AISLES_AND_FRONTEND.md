# Épica 3 — Implementation Note

## 1. Current state summary

- **Backend:** v3 has domain entities (Inventory, Aisle), application ports (InventoryRepository, AisleRepository), CreateInventory/ListInventories use cases, `/api/v3/inventories` (POST, GET), SqlInventoryRepository, MemoryInventoryRepository, centralized dependencies in `src/api/dependencies.py`. No GetInventory use case; no aisle repository implementations; no aisle endpoints. Schema already has `inventories` and `aisles` with FK and UQ(inventory_id, code).
- **Frontend:** None. No `frontend/` or `web/` directory; no existing React app. API server runs via `uvicorn src.api.server:app`.

## 2. Backend files to create

| File | Purpose |
|------|---------|
| `src/application/use_cases/get_inventory.py` | GetInventoryUseCase: repo.get_by_id(inventory_id) |
| `src/application/use_cases/create_aisle.py` | CreateAisleUseCase: check inventory exists, no duplicate code, persist Aisle with CREATED status |
| `src/application/use_cases/list_aisles_by_inventory.py` | ListAislesByInventoryUseCase: aisle_repo.list_by_inventory(inventory_id) |
| `src/infrastructure/repositories/sql_aisle_repository.py` | SqlAisleRepository: save, get_by_id, list_by_inventory, get_by_inventory_and_code; parameterized SQL; row→Aisle mapping with _ensure_utc |
| `src/infrastructure/repositories/memory_aisle_repository.py` | MemoryAisleRepository: in-memory store keyed by id; list by inventory_id filter; get_by_inventory_and_code |
| `src/api/schemas/aisle_schemas.py` | CreateAisleRequest (code), AisleResponse (id, inventory_id, code, status, created_at, updated_at, error_code, error_message) |
| `tests/application/use_cases/test_get_inventory.py` | GetInventoryUseCase: found returns entity, not found returns None (use case returns Optional or we raise in API) |
| `tests/application/use_cases/test_create_aisle.py` | CreateAisle: success, inventory not found, duplicate code |
| `tests/application/use_cases/test_list_aisles_by_inventory.py` | ListAisles: empty, non-empty, respect inventory_id |
| `tests/infrastructure/repositories/test_sql_aisle_repository.py` | Save/get_by_id, list_by_inventory, get_by_inventory_and_code, skip when DB not configured |
| `tests/api/test_aisles_v3_wiring.py` | POST aisle 201 + shape, 404 inventory not found, 409 duplicate code; GET aisles 200 + list, 404 inventory not found |

## 3. Backend files to modify

| File | Change |
|------|--------|
| `src/application/ports/repositories.py` | Add `get_by_inventory_and_code(inventory_id, code) -> Optional[Aisle]` to AisleRepository. |
| `src/api/dependencies.py` | Add get_aisle_repo (SQL when DB enabled, else memory; reuse same SqlServerClient as inventory when both SQL). Add get_get_inventory_use_case, get_create_aisle_use_case, get_list_aisles_by_inventory_use_case. |
| `src/api/schemas/inventory_schemas.py` | Add optional `created_at` (datetime) to InventoryResponse for list/detail. |
| `src/api/routes/inventories_v3.py` | Add GET `/api/v3/inventories/{inventory_id}` (404 if not found), POST/GET `/api/v3/inventories/{inventory_id}/aisles` with clear 404/409/422 handling. |
| `src/api/server.py` | No change (router already included). |

## 4. Frontend files to create

| File | Purpose |
|------|---------|
| `frontend/package.json` | React, React-DOM, React Router DOM, Material UI, Vite. |
| `frontend/vite.config.js` | Vite app, proxy /api → backend (e.g. localhost:8000). |
| `frontend/index.html` | Entry HTML with root div. |
| `frontend/src/main.jsx` | React root, Router, ThemeProvider (MUI), render App. |
| `frontend/src/App.jsx` | Routes: / → InventoriesList, /inventories/:id → InventoryDetail. |
| `frontend/src/api/client.js` | Base URL from env; getInventories(), getInventory(id), createInventory(body), getAisles(inventoryId), createAisle(inventoryId, body). |
| `frontend/src/pages/InventoriesList.jsx` | Table/cards: name, status, created_at, link to detail, button "Create inventory". |
| `frontend/src/pages/InventoryDetail.jsx` | Show inventory name, status, created_at; aisles section (table: code, status, created_at, error); "Create aisle" button. |
| `frontend/src/components/CreateInventoryDialog.jsx` | Modal: name field, validate, submit → createInventory, onSuccess close + refresh list or navigate to new inventory. |
| `frontend/src/components/CreateAisleDialog.jsx` | Modal: code field, validate, submit → createAisle, onSuccess close + refresh aisles; show duplicate-code error. |
| `frontend/.env.example` | VITE_API_BASE_URL=http://localhost:8000 |

## 5. Frontend files to modify

None (new frontend).

## 6. Repository / use-case design summary

- **AisleRepository (port):** Add `get_by_inventory_and_code(inventory_id: str, code: str) -> Optional[Aisle]` for duplicate check. Existing: save, get_by_id, list_by_inventory.
- **CreateAisleUseCase:** Input: CreateAisleCommand(inventory_id, code). Depends: InventoryRepository, AisleRepository, Clock. Steps: (1) inventory_repo.get_by_id(inventory_id) → if None, raise or return error (API will map to 404). (2) aisle_repo.get_by_inventory_and_code(inventory_id, code) → if some, duplicate (API → 409). (3) Build Aisle(id=uuid4(), inventory_id, code, status=CREATED, created_at=updated_at=now), save, return Aisle.
- **ListAislesByInventoryUseCase:** Input: inventory_id. Depends: AisleRepository. Returns list; API can 404 if inventory not found (optional: verify inventory exists via InventoryRepository in API or in use case—prefer use case or route: GET aisles can return 200 [] if inventory missing, or 404; we choose 404 for consistency so frontend can show "Inventory not found").
- **GetInventoryUseCase:** Input: inventory_id. Depends: InventoryRepository. Returns Optional[Inventory]; API returns 404 when None.
- **SqlAisleRepository:** Same client as inventory (single connection string). INSERT/UPDATE by id; list_by_inventory ORDER BY created_at DESC; get_by_inventory_and_code SELECT by inventory_id and code. Map row to Aisle with AisleStatus enum and _ensure_utc for datetimes.
- **MemoryAisleRepository:** Dict by id; list_by_inventory filters by inventory_id; get_by_inventory_and_code scans or secondary dict (inventory_id, code) → id.

## 7. Frontend design summary

- **Stack:** React 18, Vite, React Router 6, Material UI (MUI) 5.
- **Layout:** Simple top bar or title "Dinamic Inventory v3", main content area. No sidebar for now.
- **Inventories list:** MUI Table or Card list; columns: name, status, created (formatted date), action "Open". FAB or button "Create inventory" opens CreateInventoryDialog.
- **Create inventory:** Dialog with text field (name), validation (required, max 255), Cancel/Create; on success close and either refresh list or navigate to `/inventories/{id}`.
- **Inventory detail:** Breadcrumb or back link to list; display name, status, created_at; section "Aisles" with table (code, status, created_at, error_message if any), "Create aisle" button opening CreateAisleDialog.
- **Create aisle:** Dialog with code field, validation (required, max 64), duplicate error from API 409 shown as inline error; on success refresh aisles list.
- **API client:** Single module with fetch calls; parse JSON; throw on !response.ok with body for error message. Base URL from import.meta.env.VITE_API_BASE_URL.
- **Loading/empty/error:** Loading spinners on list/detail; empty state "No inventories" / "No aisles"; error state from failed fetch shown in alert or inline.

## 8. Risks / decisions

- **Single SQL client:** Reuse the same SqlServerClient for both Inventory and Aisle repos when DB is enabled (get_inventory_repo and get_aisle_repo both use it). Avoid opening two connections; keep dependency creation in dependencies.py.
- **404 for GET inventory and GET aisles when inventory missing:** GET /inventories/{id} returns 404 if inventory not found. GET /inventories/{id}/aisles returns 404 if inventory not found (so frontend does not show "empty aisles" for invalid id). CreateAisle returns 404 if inventory not found.
- **Duplicate aisle code:** CreateAisleUseCase detects via get_by_inventory_and_code; use case can raise a domain/application exception "DuplicateAisleCode" or return a result type; API maps to 409 Conflict with clear message. Decision: use case raises a small application-level exception (e.g. DuplicateAisleCodeError) so API can map to 409 without coupling to HTTP.
- **CORS:** Backend must allow frontend origin (e.g. localhost:5173). FastAPI: add CORSMiddleware in server.py for this epic.
- **Frontend tests:** Optional for this epic; no existing frontend test setup. Omit or add one smoke test if simple.
