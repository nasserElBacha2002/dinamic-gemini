# Tenant endpoint final matrix (Stage 2 corrections)

| endpoint family | control | classification | notes |
|-----------------|---------|----------------|-------|
| GET/POST /clients/ | use case + principal | FIXED | create platform-only |
| GET/PATCH /clients/{id} | ClientAccessPolicy + require_client_scope | FIXED | 404 cross-tenant |
| /clients/{id}/suppliers/** | require_client_scope Depends | FIXED | nested use-case parent checks remain |
| /clients/{id}/position-labels/** | Depends + use-case require_client_scope | CONTROL_IN_USE_CASE + FIXED | |
| /clients/{id}/product-labels | require_client_scope | FIXED | |
| GET/POST/PATCH inventories | policy / list_for_client | FIXED | |
| bulk soft-delete | soft_delete_many_for_scope txn | FIXED | |
| metrics | InventoryAccessPolicy | FIXED | |
| six priority exports | require_inventory_client_scope | FIXED | |
| aisle list/create/update/activate/deactivate/status | require_inventory_client_scope | FIXED | |
| aisle process/recover | require_inventory_client_scope | CONTROL_ALREADY_PRESENT | |
| aisle locations / assets | require_inventory_client_scope | CONTROL_ALREADY_PRESENT | |
| aisle revisions / many job routes | partial / observability guards | NEEDS_DYNAMIC_VALIDATION | not auto-claimed fixed |
| analytics / admin | unknown / platform | NEEDS_DYNAMIC_VALIDATION | |
| /auth/* | N/A | NOT_APPLICABLE | |
