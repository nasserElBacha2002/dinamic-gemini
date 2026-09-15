# Authorization model (before → after Stage 2)

## Roles

| Claim / alias | Normalized | Tenant binding |
|---------------|------------|----------------|
| `platform_admin` | platform | optional `client_id` (global) |
| `administrator` | → `platform_admin` | legacy |
| `company_admin` | company | **required** `client_id` (fail closed if missing) |
| `operator` / aliases | company-scoped capabilities | required `client_id` |

JWT `client_id` is set at login from env (`ADMIN_CLIENT_ID` / `JAIRO_CLIENT_ID`). Body `client_id` is never trusted as tenant authority.

## Resource ownership

```
Client (id)
└── Inventory (client_id)
    └── Aisle (inventory_id)
        └── Assets / Jobs / Exports / Captures / …
```

## Semantics chosen

- **401** — missing/invalid token
- **403** — authenticated but platform-only operation (e.g. create client)
- **404** — missing **or** cross-tenant resource (anti-enumeration), consistent with `InventoryAccessPolicy`

## Controls before Stage 2

- `InventoryAccessPolicy` + `require_inventory_client_scope` on ~33 nested inventory routes (CONTROL_VERIFIED)
- Soft-delete inventories already principal-aware (but partial delete on mixed IDs)
- Clients CRUD + inventory list/get/patch/metrics + exports: JWT only

## Controls after Stage 2

- `ClientAccessPolicy` for clients list/get/update; create is platform-only
- Inventory list uses `list_for_client` before pagination/totals
- Get/patch/metrics inventories require policy
- Create inventory forces body `client_id` == principal for company admins
- Soft-delete: if any ID inaccessible → **no** writes
- Six priority export routes depend on `require_inventory_client_scope` **before** streaming
