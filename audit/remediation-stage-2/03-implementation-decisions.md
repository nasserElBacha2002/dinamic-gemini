# Implementation decisions (Stage 2)

## Policies

- Reused `InventoryAccessPolicy` for inventory-rooted resources (404 cross-tenant).
- Added `ClientAccessPolicy` for clients CRUD (same 404 semantics; create → `PlatformOnlyOperationError` → HTTP 403).
- Did **not** create a third parallel tenant policy; client policy complements inventory policy.

## HTTP semantics

| Situation | Status |
|-----------|--------|
| Missing/invalid token | 401 |
| Authenticated, platform-only op (create client) | 403 |
| Missing resource or other tenant | 404 |

## Queries

- `ClientRepository.list_for_client(client_id)` / `InventoryRepository.list_for_client(client_id)` on memory + SQL.
- Company list paths use scoped list **before** sort/paginate/totals.
- Platform continues to use global `list_all` / unfiltered inventory listing.
- Body `client_id` is not trusted as tenant authority for company admins (create inventory forces match).

## Bulk soft-delete

- Resolve + authorize **all** IDs first.
- If any ID missing or not visible → return `not_found_ids` and **write nothing**.
- Duplicates deduped deterministically; empty list → `ValueError`.

## Exports

- Six priority export routes depend on `require_inventory_client_scope` **before** use-case execution / streaming.

## Out of scope (explicit)

- Worker SQL (Stage 1), frontend/mobile JWT storage, OpenAPI regen, wholesale fix of all 154 `POTENTIAL_BOLA` candidates.
