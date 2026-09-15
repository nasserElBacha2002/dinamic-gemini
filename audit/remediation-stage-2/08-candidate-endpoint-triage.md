# Candidate endpoint triage (Stage 2)

Classification keys: `VULNERABLE_CONFIRMED` (pre-fix) → post-fix status · `CONTROL_ALREADY_PRESENT` · `CONTROL_IN_USE_CASE` · `PLATFORM_ONLY` · `NOT_APPLICABLE` · `NEEDS_DYNAMIC_VALIDATION`.

Certainty: HIGH / MEDIUM / LOW.

| endpoint | role | resource scope | control anterior | control final | certeza | test asociado |
|----------|------|----------------|------------------|---------------|---------|---------------|
| GET /api/v3/clients/ | company_admin | client list | JWT only (listed A+B) | ClientAccessPolicy.list_visible + list_for_client | HIGH | test_tenant_isolation_stage2* |
| POST /api/v3/clients/ | company_admin | create | JWT only | PLATFORM_ONLY → 403 | HIGH | test_tenant_isolation_stage2_http |
| GET /api/v3/clients/{id} | company_admin | client | JWT only (cross 200) | ClientAccessPolicy.require_client → 404 | HIGH | test_tenant_isolation_stage2* |
| PATCH /api/v3/clients/{id} | company_admin | client | JWT only | ClientAccessPolicy.require_client | HIGH | test_tenant_isolation_stage2 (app) |
| GET /api/v3/inventories/ | company_admin | inventory list | JWT only | list_for_client before page/totals | HIGH | test_tenant_isolation_stage2* |
| POST /api/v3/inventories/ | company_admin | create | body client_id trusted | force claim match / fail closed | HIGH | test_create_inventory + stage2 |
| GET /api/v3/inventories/{id} | company_admin | inventory | JWT only (cross 200) | InventoryAccessPolicy in use case | HIGH | test_tenant_isolation_stage2* |
| PATCH /api/v3/inventories/{id} | company_admin | inventory | JWT only | InventoryAccessPolicy in use case | HIGH | test_update_inventory_name |
| POST …/bulk-soft-delete | company_admin | multi inventory | partial deletes possible | authorize-all else no writes | HIGH | test_soft_delete / stage2 |
| GET …/metrics | company_admin | inventory | JWT only | InventoryAccessPolicy | HIGH | test_get_inventory_metrics |
| GET …/export | company_admin | inventory | JWT only (cross 200) | require_inventory_client_scope before stream | HIGH | test_tenant_isolation_stage2_http |
| GET …/export/package | company_admin | inventory | JWT only | require_inventory_client_scope | HIGH | Depends wired; HTTP sample via inv export family |
| GET …/export/summary | company_admin | inventory | JWT only | require_inventory_client_scope | HIGH | Depends wired |
| GET …/aisles/{id}/export | company_admin | aisle export | JWT only (cross 200) | require_inventory_client_scope | HIGH | Depends + inventory export HTTP |
| GET …/aisles/{id}/benchmark/export | company_admin | aisle | JWT only | require_inventory_client_scope | HIGH | Depends wired |
| GET …/aisles/{id}/code-scans/export | company_admin | aisle | JWT only | require_inventory_client_scope | HIGH | test_code_scans_routes export |
| GET …/aisles/{id}/locations* | any | aisle | CONTROL_VERIFIED | CONTROL_ALREADY_PRESENT | HIGH | existing aisle_locations tests |
| GET …/aisles/{id}/assets* | any | aisle | CONTROL_VERIFIED | CONTROL_ALREADY_PRESENT | HIGH | existing assets tests |
| GET /api/v3/clients/{id}/suppliers* | company_admin | nested client | JWT only | NEEDS_DYNAMIC_VALIDATION | MEDIUM | — (out of Stage 2 confirmed set) |
| GET /api/v3/clients/{id}/position-labels* | company_admin | nested client | JWT only | NEEDS_DYNAMIC_VALIDATION | MEDIUM | — |
| GET /api/v3/inventories/{id}/aisles (list/create) | company_admin | nested | often no inventory Depends | NEEDS_DYNAMIC_VALIDATION | MEDIUM | — |
| Analytics /admin/* | varies | global | AUTHORIZATION_UNKNOWN | NEEDS_DYNAMIC_VALIDATION / PLATFORM_ONLY candidate | LOW | — |
| /auth/* | — | — | NOT_APPLICABLE | NOT_APPLICABLE | HIGH | — |

Remaining ~140 `POTENTIAL_BOLA` inventory rows from september inventory: **not** claimed fixed; follow inventory-rooted Depends adoption in later stages.
