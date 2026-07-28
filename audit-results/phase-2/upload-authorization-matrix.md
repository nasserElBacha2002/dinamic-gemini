# Upload Authorization Matrix (Phase 2)

| Resource | Create/Upload | Read | Delete | Process |
|----------|---------------|------|--------|---------|
| Inventory-rooted aisle assets | `require_inventory_client_scope` before spool + use-case scope | List/file/display with `access_user` | Delete with `access_user` | `StartAisleProcessingCommand.access_user` |
| Capture session staging | Same inventory scope before spool | Session detail (inventory exists) | N/A | Materialize via inventory/aisle scope |

## Policy

- Actor from JWT (`get_current_admin`).
- Company roles: inventory.`client_id` must match actor.`client_id` (404 on mismatch — existence not leaked).
- Platform admin: global scope.
- Hierarchy: inventory → aisle → asset/session.

## IDOR tests

`backend/tests/application/use_cases/test_upload_client_scope_phase2.py`
