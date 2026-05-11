# G7.0 — Phase G final audit

## 1. Executive summary

**Status: `G7_0_READY_WITH_OBSERVATIONS`**

Static review and targeted tests confirm **client-oriented enforcement**, **supplier-scoped references**, **supplier prompt resolution**, and **non-silent missing-config behavior** (G6). **SQL Server** was not reachable for NULL-count / migration validation in this workspace — operators should run **`audit/raw/phase-g/g7-0-db-checks.sql`**.

## 2. Backend architecture validation

| Area | State |
| --- | --- |
| Inventory create | **`client_id`** required for new inventories (G2) |
| Aisle create | **`client_supplier_id`** required when inventory has client (G3) |
| Reference images | **`supplier_reference_images`** canonical path (G5) |
| Prompt configs | **`supplier_prompt_configs`** + resolver precedence |
| Missing active prompt | **Fails job by default**; env emergency override documented (G6) |
| Legacy `inventory_visual_references` | No Python `src` usage; migration **0029** when empty |

## 3. Frontend architecture validation

| Area | State |
| --- | --- |
| Create inventory / aisle | Prior G2/G3 UX |
| Supplier detail | Active prompt **404** warning (G6.2) |
| Job / aisle observability | Fallback + error trace strings (G6.2) |

## 4. Database constraint validation

- **NOT NULL** on `inventories.client_id` / `aisles.client_supplier_id`: **verify in deployed DB** (G4 completion is environment-specific).
- Use **`g7-0-db-checks.sql`** for NULL counts.

## 5. Legacy cleanup validation

- **`inventory_visual_references`**: deprecated/removed from active code per G5 audit trail.

## 6. Prompt fallback validation

- **Default:** missing active supplier prompt config ⇒ **blocked** with **`NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`**.
- **Emergency:** **`V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK`**.

## 7. Observability / metadata validation

- **`effective_prompt_hash`**, **`protected_prompt_contract_*`**, **`fallback_used`**, **`fallback_reason`**, **`resolution_status`**, **`resolution_error_code`** remain in composition/trace paths.

## 8. Test and validation results

See **`audit/raw/phase-g/g7-0-validation.txt`** and **`g6-3-validation.txt`**.

## 9. Remaining risks

- DB connectivity for drift / constraint verification.
- Operators must configure supplier prompts before processing in normal environments.

## 10. Closure recommendation

Proceed to **`g7-phase-g-final-closure.md`**. **G7.1** skipped — no additional blocking fixes beyond G6 scope.
