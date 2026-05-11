# F1 — Navigation and information architecture audit

**Date:** 2026-05-11  
**Scope:** `frontend/src` routing, primary pages, shell navigation (pre–Phase F implementation).

## 1. Routes currently registered (`App.tsx`)

| Path (relative to `/`) | Page / element |
|------------------------|----------------|
| `login` | `LoginPage` (outside shell) |
| `/` (index) | `InventoriesList` |
| `inventories` | `InventoriesList` |
| `review-queue` | `ReviewQueuePage` |
| `metrics` | `MetricsPage` |
| `clientes` | `ClientsList` |
| `clientes/:clientId` | `ClientDetail` |
| `ingestion-sessions` | `IngestionSessionsPage` |
| `ingestion-sessions/:sessionId` | `IngestionSessionDetailPage` |
| `admin/ai-config` | `AdminAiConfigPage` (admin user) |
| `inventories/:inventoryId` | `InventoryDetail` |
| `inventories/:inventoryId/aisles/:aisleId/positions` | `AislePositionsPage` |
| `inventories/:inventoryId/analytics/compare` | `CompareRunsPage` |
| `inventories/:inventoryId/analytics/compare-many` | `CompareManyRunsPage` |
| `inventories/:inventoryId/aisles/:aisleId/compare` | `LegacyAisleCompareRedirect` |
| `inventories/:inventoryId/aisles/:aisleId/positions/:positionId` | `PositionDetailPage` |
| `inventories/:inventoryId/aisles/:aisleId/observability` | `AisleObservabilityPage` |
| `dashboard`, `settings` | Redirect → home |

**Note:** There was **no** dedicated supplier URL before Phase F; suppliers were edited only from `ClientDetail` (table + drawers).

## 2. Where are clients listed?

- **Route:** `/clientes` → `ClientsList.tsx`  
- **Nav:** Primary drawer → “Clientes” (`nav.clients`).

## 3. Where is client detail shown?

- **Route:** `/clientes/:clientId` → `ClientDetail.tsx`  
- **Entry:** Clients list (name link, “Ver detalle”), direct URL.

## 4. Where are client suppliers listed?

- **Embedded** in `ClientDetail` → section “Proveedores” with `DataTable` of `ClientSupplier` rows.  
- Prompt configs / reference images open as **modules (drawers)**, not separate routes.

## 5. Where is supplier detail shown?

- **Before F1:** No full-page supplier detail; only **drawers** (`SupplierPromptConfigsModule`, `SupplierReferenceImagesModule`) from action buttons on the client’s supplier table.

## 6. Can the user navigate client → supplier?

- **Table + drawers:** Yes (configure prompt / manage images).  
- **Dedicated supplier page:** Added in Phase F (`/clientes/:clientId/proveedores/:supplierId`).

## 7. Can the user navigate client → inventories?

- **Before F1:** No first-class list on `ClientDetail` (API list inventories has no `client_id` filter; would require client-side filter or new API).  
- **Phase F:** `ClientDetail` loads inventories with `useInventoriesList` (large page size) and filters by `client_id` for a **“Inventarios del cliente”** section with links to `pathToInventory`.

## 8. Can the user navigate inventory → client?

- **Before F1:** `InventoryDetailHeader` had breadcrumbs only **Inventarios** → inventory title; no client link.  
- **Phase F:** When `inventory.client_id` is set, breadcrumbs include **Clientes** → **client name** (link) → inventory name; optional `useClient` for resolved name.

## 9. Can the user navigate aisle → supplier?

- **Before F1:** Aisle row had no supplier column; `client_supplier_id` existed on `Aisle` but was not surfaced in the grid.  
- **Phase F:** `InventoryAislesSection` receives `inventoryClientId` and shows **Proveedor del pasillo** with link to supplier detail when both IDs exist.

## 10. Can the user navigate aisle/job → observability page?

- **Yes:** Row actions → “Ver observabilidad” → `pathToAisleObservability(inventoryId, aisleId, initialJobId)` (`InventoryAislesSection`).

## 11. Which screens had breadcrumbs?

| Screen | Breadcrumbs (before F1) |
|--------|-------------------------|
| `InventoryDetail` | **Inventarios** → (inventory title via `InventoryDetailHeader`) |
| `ClientsList` | None (PageHeader actions only) |
| `ClientDetail` | None (back button to list only) |
| `AisleObservabilityPage` | Check workspace component |

## 12. Which screens felt disconnected or orphaned?

- **Supplier configuration** lived only in **drawers** on `ClientDetail` — no shareable URL or deep link for “this supplier”.  
- **Client ↔ inventory** relationship was not visible from **client** or **inventory** list/detail in a unified way.  
- **Aisles** did not show **supplier** context in the main inventory table.

## Phase F F1 remediation summary

1. Add **`ClientSupplierDetail`** route + `pathToClientSupplier` + topbar copy.  
2. **`ClientDetail`:** breadcrumbs **Clientes → {cliente}**; supplier name cell links to supplier page; **inventarios del cliente** section + **Crear inventario** (prefilled client).  
3. **`ClientsList`:** client-side **search** on current page + toolbar hint.  
4. **`InventoryDetail`:** legacy **sin cliente** alert; header breadcrumbs extended with client when present.  
5. **`InventoryAislesSection`:** supplier column + observability unchanged.

## Recommendation

**READY_FOR_NEXT_F_SUBPHASE** (F2) after F1 merge, pending full `npm test` in CI.
