# Handoff — Stage 2 tenant isolation / BOLA

## Stage status

**IMPLEMENTED_WITH_LIMITATIONS**

## Done

- Client + inventory CRUD/list/metrics/bulk-delete tenant enforcement via `ClientAccessPolicy` / `InventoryAccessPolicy`.
- `list_for_client` on memory + SQL client/inventory repos; lists scoped before pagination.
- Priority export routes gated by `require_inventory_client_scope` before streaming.
- Unit, HTTP, and SQL A/B tests added; ruff + mypy scoped green.
- Audit package under `audit/remediation-stage-2/`.

## Not done / next

1. Run DAST A/B on **LOCAL_ISOLATED_ONLY** using matrix in `05-dast-regression-results.md`.
2. Ensure a **single** full `pytest` run is green end-to-end (first run had 2 error_mapping stub failures; fixed).
3. Apply `ClientAccessPolicy` to nested client suppliers / position-labels.
4. Systematically add `require_inventory_client_scope` (or use-case policy) to remaining aisle-rooted `POTENTIAL_BOLA` routes.
5. Optional: SQL-level scoped soft-delete; hash client_id in denial logs.

## Do not mix

- Stage 1 worker SQL claim changes.
- Frontend JWT storage / mobile deps / OpenAPI cosmetic work.
