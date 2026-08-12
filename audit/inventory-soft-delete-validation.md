# Inventory soft delete — validation

**Date:** 2026-08-12
**Feature:** Soft delete de inventarios con selección múltiple en listado UI

## 1. Archivos modificados / creados

### Backend
- `backend/src/database/migrations/versions/0096_inventories_soft_delete.sql` (+ `.down.sql`)
- `backend/src/database/schema.sql` (mirror `deleted_at` / `deleted_by`)
- `backend/src/domain/inventory/entities.py` (`deleted_at`, `deleted_by`, `mark_deleted`)
- `backend/src/application/services/inventory_soft_delete.py`
- `backend/src/application/services/inventory_access_policy.py` (reject deleted)
- `backend/src/application/use_cases/inventories/soft_delete_inventories.py`
- `backend/src/application/use_cases/inventories/get_inventory.py`
- `backend/src/application/use_cases/inventories/get_inventory_metrics.py`
- `backend/src/application/use_cases/inventories/update_inventory_name.py`
- `backend/src/application/ports/repositories.py` (`list_all` contract)
- `backend/src/infrastructure/repositories/sql_inventory_repository.py`
- `backend/src/infrastructure/repositories/memory_inventory_repository.py`
- `backend/src/api/schemas/inventory_schemas.py`
- `backend/src/api/routes/v3/inventories.py`
- `backend/src/api/dependencies.py`
- `backend/tests/application/use_cases/test_soft_delete_inventories.py`

### Frontend
- `frontend/src/pages/InventoriesList.tsx`
- `frontend/src/api/inventoriesApi.ts` / `client.ts`
- `frontend/src/hooks/useMutations.ts` / `hooks/index.ts`
- `frontend/src/components/ui/DataTable.tsx` (`label: ReactNode`)
- `frontend/src/i18n/locales/es|en/translation.json`
- `frontend/tests/InventoriesListPage.test.tsx`

## 2. Migración

- **Version:** `0096_inventories_soft_delete`
- **Columns:** `deleted_at DATETIME2 NULL`, `deleted_by VARCHAR(64) NULL`
- **Index:** filtered `IX_inventories_deleted_at` WHERE `deleted_at IS NULL`
- Existing rows remain active (`deleted_at` NULL). No destructive backfill.

## 3. Endpoint

```http
POST /api/v3/inventories/bulk-soft-delete
```

Body: `{ "inventory_ids": ["…"] }`
Response: `{ deleted_ids, already_deleted_ids, not_found_ids }`

Requires admin auth (router `get_current_admin`). Uses `AccessPrincipal` for scope.

## 4. Autorización

- Platform: any inventory id.
- Company-scoped: only inventories whose `client_id` matches principal; mismatches → `not_found_ids` (no leak).
- Nested inventory routes via `InventoryAccessPolicy.require_inventory` treat soft-deleted as 404.

## 5. Exclusión de eliminados

- `list_all()` / listado paginado: `deleted_at IS NULL` (SQL + memory).
- `GetInventory`, metrics, update name: `reject_if_inventory_deleted`.
- `get_by_id` still returns deleted rows so in-flight workers can finish (no auto-cancel jobs).

## 6. Idempotencia

Re-delete already soft-deleted → `already_deleted_ids`; `deleted_at` / `deleted_by` unchanged.

## 7. Impacto mobile

No UI change. `GET /api/v3/inventories` already excludes deleted; mobile list hides them automatically. Direct deep-link to deleted id → 404 like web.

## 8. Tests ejecutados

| Suite | Result |
| ----- | ------ |
| `pytest …/test_soft_delete_inventories.py` + related inventory tests | **31 passed** |
| `vitest tests/InventoriesListPage.test.tsx` | **6 passed** |
| `ruff check` (touched backend files) | **PASS** |
| `mypy` (core soft-delete modules) | **PASS** |

## 9. Resultados

Soft delete implemented without physical DELETE. UI selection + ConfirmDialog + bulk API wired.

## 10. Riesgos / pendientes

- Apply migration `0096` on each environment before deploying API that writes `deleted_at`.
- No restore UI/API in this phase (restore = clear `deleted_at` later).
- In-flight jobs on soft-deleted inventories continue; new ops via API are blocked.
- List remains unfiltered by tenant for platform admins (pre-existing behavior).
