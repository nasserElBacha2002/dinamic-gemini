# Épica 3 — Implementation Summary

## 1. What was implemented

- **Backend**
  - **AisleRepository:** Port extended with `get_by_inventory_and_code(inventory_id, code)`; implemented by `SqlAisleRepository` and `MemoryAisleRepository`. SQL implementation uses parameterized queries, domain-owned timestamps, and deterministic `list_by_inventory` ordering (`created_at DESC`).
  - **Aisle use cases:** `CreateAisleUseCase` (checks parent inventory exists, rejects duplicate code via `get_by_inventory_and_code`, creates Aisle with status CREATED) and `ListAislesByInventoryUseCase`. Application exceptions `InventoryNotFoundError` and `DuplicateAisleCodeError` for API mapping to 404/409.
  - **GetInventoryUseCase:** Returns a single inventory by id for the detail page and for “inventory exists” checks on aisle endpoints.
  - **v3 API:** `GET /api/v3/inventories/{inventory_id}` (404 if not found), `POST /api/v3/inventories/{inventory_id}/aisles` (201/404/409/422), `GET /api/v3/inventories/{inventory_id}/aisles` (200/404). Request validation for aisle code (min/max length). `InventoryResponse` extended with optional `created_at`.
  - **Dependencies:** Shared `_get_v3_sql_client()` for inventory and aisle SQL repos; `get_aisle_repo`, `get_get_inventory_use_case`, `get_create_aisle_use_case`, `get_list_aisles_by_inventory_use_case` in `dependencies.py`. CORS enabled for `localhost:5173` / `127.0.0.1:5173`.
  - **Tests:** GetInventoryUseCase, CreateAisleUseCase (success, inventory not found, duplicate code), ListAislesByInventoryUseCase; API wiring for get inventory, post/list aisles, 404/409/422; SQL AisleRepository integration tests (when DB configured).

- **Frontend**
  - **Stack:** React 18, Vite 5, React Router 6, Material UI 5.
  - **Pages:** Inventories list (table: name, status, created, Open; Create inventory button); Inventory detail (name, status, created; aisles table with code, status, created, error; Create aisle button).
  - **Flows:** Create inventory (dialog → success navigates to detail or refreshes list); Create aisle (dialog → duplicate code error from 409; success refreshes aisles list). Loading, empty, and error states on list and detail.
  - **API client:** `frontend/src/api/client.js` with `getInventories`, `getInventory`, `createInventory`, `getAisles`, `createAisle`; proxy in Vite config for `/api` → backend.

---

## 2. Backend files created

| File | Purpose |
|------|---------|
| `src/application/use_cases/get_inventory.py` | GetInventoryUseCase |
| `src/application/use_cases/create_aisle.py` | CreateAisleUseCase + InventoryNotFoundError, DuplicateAisleCodeError |
| `src/application/use_cases/list_aisles_by_inventory.py` | ListAislesByInventoryUseCase |
| `src/infrastructure/repositories/sql_aisle_repository.py` | SqlAisleRepository |
| `src/infrastructure/repositories/memory_aisle_repository.py` | MemoryAisleRepository |
| `src/api/schemas/aisle_schemas.py` | CreateAisleRequest, AisleResponse |
| `tests/application/use_cases/test_get_inventory.py` | GetInventory use case tests |
| `tests/application/use_cases/test_create_aisle.py` | CreateAisle use case tests |
| `tests/application/use_cases/test_list_aisles_by_inventory.py` | ListAisles use case tests |
| `tests/infrastructure/repositories/test_sql_aisle_repository.py` | SqlAisleRepository integration tests |
| `tests/api/test_aisles_v3_wiring.py` | API wiring for get inventory + aisle endpoints |

---

## 3. Backend files modified

| File | Change |
|------|--------|
| `src/application/ports/repositories.py` | Added `get_by_inventory_and_code(inventory_id, code) -> Optional[Aisle]` to AisleRepository |
| `src/api/dependencies.py` | Shared `_get_v3_sql_client()`, `get_aisle_repo`, get_get_inventory_use_case, get_create_aisle_use_case, get_list_aisles_by_inventory_use_case |
| `src/api/schemas/inventory_schemas.py` | Added optional `created_at` to InventoryResponse |
| `src/api/routes/inventories_v3.py` | GET `/{inventory_id}`, POST/GET `/{inventory_id}/aisles`; 404/409 handling; response helpers with created_at |
| `src/api/server.py` | CORSMiddleware for localhost:5173 / 127.0.0.1:5173 |

---

## 4. Frontend files created

| File | Purpose |
|------|---------|
| `frontend/package.json` | React, React Router, MUI, Vite |
| `frontend/vite.config.js` | Proxy /api, /health to backend |
| `frontend/index.html` | Entry HTML |
| `frontend/src/main.jsx` | Root, Router, ThemeProvider, CssBaseline |
| `frontend/src/theme.js` | MUI theme |
| `frontend/src/App.jsx` | Routes: / → InventoriesList, /inventories/:inventoryId → InventoryDetail |
| `frontend/src/api/client.js` | getInventories, getInventory, createInventory, getAisles, createAisle |
| `frontend/src/pages/InventoriesList.jsx` | List + Create inventory button + CreateInventoryDialog |
| `frontend/src/pages/InventoryDetail.jsx` | Inventory header + aisles table + Create aisle button + CreateAisleDialog |
| `frontend/src/components/CreateInventoryDialog.jsx` | Name field, validation, submit, success/error |
| `frontend/src/components/CreateAisleDialog.jsx` | Code field, validation, 409 duplicate error, submit |
| `frontend/.env.example` | VITE_API_BASE_URL |
| `frontend/README.md` | Setup, dev, build, env |
| `docs/V3/IMPLEMENTATION_NOTE_EPICA3_AISLES_AND_FRONTEND.md` | Implementation note (pre-coding) |

---

## 5. Frontend files modified

None (new frontend).

---

## 6. Architectural decisions made

- **Shared SQL client:** One `_get_v3_sql_client()` used by both Inventory and Aisle repos when DB is enabled to avoid multiple connections and keep initialization in one place.
- **Application exceptions for aisle creation:** `InventoryNotFoundError` and `DuplicateAisleCodeError` raised by CreateAisleUseCase so the API can map to 404 and 409 without coupling use cases to HTTP.
- **GET aisles returns 404 when inventory missing:** Frontend can show “Inventory not found” instead of an empty list for invalid ids.
- **CORS:** Allowed only for dev origins (localhost:5173, 127.0.0.1:5173); production should restrict origins.
- **Frontend proxy:** Vite proxies `/api` and `/health` to the backend so the app works with a single origin in development; optional `VITE_API_BASE_URL` for production or different ports.

---

## 7. Intentionally deferred

- **Frontend unit tests:** No Jest/Vitest or component tests in this epic; optional for a later slice.
- **Inventory response `created_at` in existing POST/GET list:** Already returned; no breaking change. Optional field for backward compatibility.
- **Aisle “Action” column:** Placeholder “—” for future flows (e.g. open aisle, upload assets).
- **Lifespan events:** FastAPI `on_event("startup")` deprecation not addressed; can be moved to lifespan in a later cleanup.

---

## 8. Recommended next slice

- **Processing / jobs / review (Épica 4):** Connect v3 inventories/aisles to the existing job pipeline (e.g. create job for an aisle, list jobs by inventory/aisle), or add asset upload and queue flows for aisles.
- **Optional short follow-ups:** GET single aisle by id if the UI needs it; pagination for list inventories/aisles when data grows; frontend tests and E2E if the project adopts a frontend test stack.
