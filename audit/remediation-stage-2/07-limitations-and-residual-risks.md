# Limitations and residual risks (Stage 2)

## Status gate

**IMPLEMENTED_WITH_LIMITATIONS** — confirmed families hardened; formal DAST A/B not run; first full pytest not green.

## Residual risks

1. **Nested `/clients/{client_id}/suppliers…` and position-labels** — still largely JWT-auth only; path `client_id` may not go through `ClientAccessPolicy` on every handler. Triaged as `NEEDS_DYNAMIC_VALIDATION` / follow-up stage.
2. **Many inventory-nested routes** still marked `POTENTIAL_BOLA` in endpoint inventory (aisle CRUD without `require_inventory_client_scope`, revisions, analytics, etc.). Not auto-patched.
3. **Soft-delete atomicity** is application-level (authorize-all-then-write), not a single SQL `UPDATE … WHERE client_id = @cid` transaction. Concurrent writers could still race; no partial cross-tenant success in the use case path.
4. **Inventories with NULL `client_id`** — company_admin fail-closed (404); platform still sees them. No automatic tenant assignment.
5. **`company_admin` without `client_id`** — empty lists / 404 / fail closed; no self-heal.
6. **Denial logs** include `principal_client_id` plaintext (not hashed) in `ClientAccessPolicy`; inventory policy uses legacy `cross_client_access_denied` event name.
7. **`ClientAccessPolicy.list_visible`** has a `getattr(…, "list_for_client")` fallback for older fakes — prefer explicit port methods only.
8. **DAST LOCAL_ISOLATED** not executed this session.
9. **Parent A + child B** on every nested surface not exhaustively tested; priority exports covered via inventory scope Depends + existing aisle scope helpers where wired.

## Explicitly unchanged

- Stage 1 worker SQL claim path.
- Frontend / mobile auth storage.
- OpenAPI regeneration.
