# Stage 2 corrections — implementation decisions

## Status target

`CORRECTED_WITH_LIMITATIONS` (DAST LOCAL_ISOLATED_ONLY not executed in this session).

## Decisions

1. **Fail-open removed** — `ListInventoryListItemsUseCase.execute` requires `principal: AccessPrincipal` (no `None` → platform).
2. **Client root** — new FastAPI `require_client_scope` dependency; applied to all `/{client_id}/**` handlers in `clients.py`, `client_position_labels.py`, `client_product_labels.py`. Position-label use cases already had `require_client_scope` in-application; Depends adds defense in depth.
3. **Supplier nested** — route-level ClientAccessPolicy only in this correction; use cases still check client exists / supplier.parent. Parent/child supplier mismatch remains in existing supplier helpers.
4. **Inventory priority aisles** — `require_inventory_client_scope` added to create/update/activate/deactivate/list/status (exports already gated).
5. **Soft-delete** — `InventoryRepository.soft_delete_many_for_scope`; Memory uses store lock; SQL uses `begin_transaction` + `UPDLOCK` + scoped `UPDATE … AND client_id = ?` for company admins. Use case no longer loops `save()`.
6. **Create inventory order** — tenant/principal/client existence validated before operational resolver.
7. **Logs** — denial logs emit `event=authorization_denied`, `reason_code`, `principal_role`, `resource_type`, `operation` without raw client/resource IDs.
8. **getattr removed** — `ClientAccessPolicy.list_visible` calls `list_for_client` on the typed port.
9. **JWT HTTP tests** — new suite clears API conftest admin override and uses `create_access_token`.
10. **SQL cleanup** — fixtures deleted in `finally`; residual count asserted.

## Explicitly not done (limitations)

- Formal DAST A/B against LOCAL_ISOLATED stack.
- All remaining ~140 `POTENTIAL_BOLA` aisle/job/revision routes.
- Scoped SQL `UPDATE` for every inventory/client PATCH (soft-delete + policy remain primary write hardening).
- Concurrent bulk stress / induced mid-tx failure harness beyond mixed-id atomicity.
