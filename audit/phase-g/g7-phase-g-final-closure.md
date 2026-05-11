# G7 — Phase G final closure

## 1. Executive summary

**Status: `PHASE_G_CLOSED_WITH_OBSERVATIONS`**

Phase **G** hardening objectives are met in **code and tests**. **Observations:** production **database** constraints and row-level metrics must be validated on the live SQL Server using the provided **SQL checklists**; local drift script reports **`db_connected=false`** in this workspace.

## 2. Phase G scope recap

| Subphase | Focus |
| --- | --- |
| **G0** | Read-only audit / plan |
| **G1** | Drift metrics |
| **G2** | **`client_id`** on new inventories |
| **G3** | **`client_supplier_id`** on new aisles |
| **G4** | DB NOT NULL readiness / migrations *(verify on target DB)* |
| **G5** | Legacy **`inventory_visual_references`** deprecation/removal path |
| **G6** | **Explicit** supplier prompt fallback policy |
| **G7** | Closure audit *(this document)* |

## 3. Final architecture state

```
Client
└── Client Supplier
    ├── supplier_reference_images
    └── supplier_prompt_configs

Inventory → Client
Aisle → Client Supplier

Pipeline → EffectivePromptComposer
  ├── Protected prompt contract (always)
  ├── Supplier instructions (when resolved + non-empty)
  └── Provider/model normalization (adapters unchanged)
```

## 4. Backend final state

- Inventory/aisle **write** enforcement consistent with G2/G3.
- **Supplier prompt**: missing active config **`NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`** stops v3 jobs unless **`V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK`** is enabled.
- **Legacy inventory visual references** table not used by application Python code.

## 5. Frontend final state

- Supplier summary warns when **no active prompt** (404).
- Observability trace maps backend **enum** fallback reasons and shows resolver **error** detail in Spanish.

## 6. Database final state

- **Canonical schema mirror** excludes legacy inventory visual reference table post-migration apply.
- **NULL counts / NOT NULL**: operator-verified per environment (**`g7-0-db-checks.sql`**).

## 7. Legacy compatibility retained

- Historical jobs/logs with **`visual_reference_*`** metadata remain readable.
- Legacy inventory/aisle **fallback** resolver statuses (**inventory without client**, **aisle without supplier**) still **`fallback`** — not upgraded to hard errors in G6 (narrow change: missing **supplier prompt config** only).

## 8. Observability and support readiness

Auditable fields include: **`client_id`**, **`client_supplier_id`**, **`supplier_prompt_config_id/version`**, **`protected_prompt_contract_key/version`**, **`effective_prompt_hash`**, **`fallback_used`**, **`fallback_reason`**, **`resolution_status`**, **`resolution_error_code`**, provider/model on jobs.

## 9. Validation summary

| Layer | Command / artifact |
| --- | --- |
| Backend pytest | `audit/raw/phase-g/g6-3-validation.txt` |
| Frontend | typecheck, lint, build, ClientSupplierDetail tests |
| Drift | `python scripts/client_oriented_drift_report.py` → **db disconnected** |
| SQL checklist | `audit/raw/phase-g/g7-0-db-checks.sql` |

## 10. Known observations / residual risks

- **DB offline** in CI/developer sandbox for authoritative counts.
- Emergency env flag must be governed operationally.

## 11. Recommendation for Phase H

Move to **Phase H — Observability & operations**: dashboards for prompt-config coverage, blocked-job reasons (`NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`), client/supplier/provider metrics, run auditability.

## 12. Final recommendation

**`PHASE_G_CLOSED_WITH_OBSERVATIONS`** — closure approved from a **repository** perspective; **production** sign-off requires **DB** checklist execution.
