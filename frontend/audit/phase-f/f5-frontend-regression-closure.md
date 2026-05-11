# F5 — Frontend regression closure (Phase F — partial)

**Date:** 2026-05-11  
**Recommendation:** `PHASE_F_NEEDS_FIXES` for **global** Phase F closure (F2–F4 depth, full `npm test`, manual QA).  
**This slice:** F1 navigation + supplier detail route + inventory/client wiring is **implemented and typechecked**.

## Validation run (this change set)

| Command | Result |
|---------|--------|
| `npm run typecheck` | Pass |
| `npm run lint` | Pass (after hook-deps fix on `ClientsList`) |
| `npm run build` | Pass (see terminal) |
| `npx vitest run tests/InventoryDetailPage.test.tsx` | Pass (20 tests) |

**Not run in this session:** full `npm test` (entire suite).

## Manual QA checklist

| Flow | Status |
|------|--------|
| Clients list search / empty / error | Not executed manually |
| Client detail → supplier page → modules | Not executed manually |
| Client detail → create inventory (prefill client) | Not executed manually |
| Inventory detail breadcrumbs + legacy warning | Not executed manually |
| Aisle row → supplier link when `client_id` + `client_supplier_id` | Not executed manually |

## Remaining frontend debt

1. **F2 / F3:** Deeper empty/error/disabled copy and observability tab polish (status translators, attachments/traceability labels) as in the master Phase F spec.
2. **F4:** Repository-wide removal of legacy English values inside `es/translation.json` (grep-driven).
3. **API:** Inventory list has no `client_id` filter; client inventories section uses **page 1, size 200** + client-side filter.

## Next phase

Proceed to **Phase G** only after completing F2–F5 scope and full regression per product sign-off.
