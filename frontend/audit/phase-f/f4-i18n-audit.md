# F4 — Spanish i18n audit (Phase F slice)

**Date:** 2026-05-11  
**Scope:** New and touched Phase F surfaces (navigation, client/supplier/inventory, aisle supplier column, supplier detail page).

## Checks performed

1. **New UI strings** were added under `clients.*`, `inventory.*` (aisle supplier column + legacy warning), and `routes.client_supplier_detail` in `frontend/src/i18n/locales/es/translation.json` only (no hardcoded Spanish in those blocks except where the project already used patterns like `WizardModal`).
2. **Known pre-existing English** in `translation.json` (e.g. `aisle.reference_usage.*`, `aisle.operational_updated_snackbar`, admin keys) was **not** bulk-edited in this phase to avoid unrelated churn; they remain tracked debt for a dedicated i18n sweep.
3. **Technical JSON panels** (observability raw payloads) are unchanged by F1; labels around them should remain Spanish per prior F0.2 work.

## Findings

| Area | Status |
|------|--------|
| New routes / breadcrumbs / supplier page | Spanish keys added |
| Legacy inventory warning | Spanish |
| Clients list search hint | Spanish |
| Supplier column + link labels | Spanish |

## Recommendation

**READY_FOR_NEXT_F_SUBPHASE (F5)** for full-repo grep cleanup of legacy English keys (optional follow-up PR).
