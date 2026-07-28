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

`backend/tests/application/use_cases/test_upload_client_scope_phase2.py` (use-case level)
`backend/tests/api/test_capture_session_upload_prespool_auth_phase2.py` (HTTP level, real `TestClient`)

## Pre-spool HTTP findings (Phase 2 correction)

Verified with a real FastAPI `TestClient` (dependency-solving order matters here, not just
route-body order — see the new test module's docstring for the full FastAPI mechanics):

- **Capture session staging upload** (`require_capture_session_upload_scope`) validates the
  *full* inventory → aisle → session hierarchy as a single dependency, before the route body
  runs. All cross-hierarchy cases — session in a different inventory, aisle in a different
  inventory, session/aisle mismatch within the same inventory, nonexistent session, and
  cross-client company actor — return 404/`CAPTURE_SESSION_NOT_FOUND` / `AISLE_NOT_FOUND` /
  `INVENTORY_NOT_FOUND` with **zero** calls to the multipart spool
  (`_upload_files_to_staging_dtos`), zero artifact-storage writes, and zero persisted rows.
- **Aisle asset upload** (`require_inventory_client_scope`) only validates actor → client →
  inventory scope pre-spool; it is **not** aisle-aware. When the `aisle_id` in the path belongs
  to a *different* inventory than the path's `inventory_id`, the client-scope dependency passes
  and the route spools the multipart parts (`read_uploaded_files_for_aisle_asset_upload` **does**
  run) before `UploadAisleAssetsUseCase.execute` catches the aisle-ownership mismatch via its own
  `access_policy.require_aisle(...)` call ("before any storage writes", per that use case's inline
  comment) and returns 404/`AISLE_NOT_FOUND`. Net effect is unchanged for storage/DB (zero
  artifact-storage writes, zero persisted `SourceAsset` rows), but the spool step itself is not
  skipped for this one cross-hierarchy shape. Cross-*client* denial (company actor, wrong
  `client_id`) is still caught pre-spool since that is exactly what `require_inventory_client_scope`
  checks.
