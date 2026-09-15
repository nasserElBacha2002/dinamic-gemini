# Resource scope matrix (Stage 2)

Semantics: **401** unauthenticated · **403** platform-only denied · **404** missing or cross-tenant (anti-enumeration).

| Operation | platform_admin | company_admin own | company_admin other | company_admin no client_id | no/invalid token |
|-----------|----------------|-------------------|---------------------|----------------------------|------------------|
| GET /clients/ | all clients | only own | — | empty list | 401 |
| POST /clients/ | 201 | 403 | 403 | 403 | 401 |
| GET /clients/{id} | 200 any | 200 own | 404 | 404 | 401 |
| PATCH /clients/{id} | 200 any | 200 own | 404 | 404 | 401 |
| GET /inventories/ | all | scoped list + totals | — | empty | 401 |
| POST /inventories/ | any client_id | body client_id must match claim | 404/reject | fail closed | 401 |
| GET /inventories/{id} | 200 | 200 own | 404 | 404 | 401 |
| PATCH /inventories/{id} | 200 | 200 own | 404 | 404 | 401 |
| POST bulk-soft-delete | atomic | atomic own only | any foreign id → **no writes** | no writes | 401 |
| GET …/metrics | 200 | own | 404 | 404 | 401 |
| GET …/export (+ package/summary) | 200 | own | 404 before stream | 404 | 401 |
| GET …/aisles/{id}/export (+ benchmark, code-scans) | 200 | own inv | 404 before stream | 404 | 401 |

## Ownership tree

```
Client.id
└── Inventory.client_id
    └── Aisle.inventory_id
        └── Asset / Job / CaptureSession / Export / Position / Result
```

Parent authorization alone does not prove child membership; aisle/export routes that use `require_inventory_client_scope` still require aisle→inventory checks in use cases where applicable.
