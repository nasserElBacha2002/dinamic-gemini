# Release 3.2.5 — Phase 6: Review Operational Consistency

## Scope

This document defines the operator-facing operational contract for manual review/corrections in v3:

- what each review action changes,
- what is persisted,
- what must be visible after reread (list + detail),
- how corrected state relates to review history,
- and which limitations are deferred.

This phase is about **operational consistency only** (review write → reread → visible result). It does not redesign workflows, permissions, or evidence UX.

---

## Active v3 review actions

**Endpoint**: `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews`

**Action types**: `confirm`, `update_quantity`, `update_sku`, `delete_position`

Each successful request persists a `ReviewAction` with `before_json` and `after_json` for auditability.

---

## Implementation note (Phase 6 implementation pass)

The following was implemented to make the manual review flow operationally coherent:

1. **`needs_review` cleared after successful manual actions**  
   After any successful `confirm`, `update_quantity`, `update_sku`, or `delete_position`, the backend sets `position.needs_review = False` before saving. This prevents filters/KPIs from contradicting the operator-visible state (reviewed/corrected/deleted).

2. **Visible SKU updated on reread after `update_sku`**  
   The visible `position.sku` in list/detail is derived from `position.detected_summary_json.internal_code`. The `UpdateProductSkuUseCase` now updates this backing value (initializing or copying `detected_summary_json` as needed) so that list and detail reread show the new SKU and stay aligned with the review action’s `after_json.sku`.

3. **Review API tests aligned to real contract**  
   Tests in `backend/tests/api/test_review_actions_api.py` were updated to:
   - Assert only the actual v3 detail contract (`position`, `evidences`, `review_actions`; no `products`).
   - Seed `position.detected_summary_json` with `internal_code` so `update_sku` visible-SKU behaviour is testable.
   - Validate list and detail reread for all four actions, including `needs_review == false` and, for `update_sku`, visible `position.sku` matching the new value.

---

## Reread guarantees (after implementation)

| Action            | List reread                                      | Detail reread                                      | needs_review |
|-------------------|--------------------------------------------------|----------------------------------------------------|--------------|
| `confirm`         | `status == "reviewed"`                           | same + `review_actions` contains confirm           | `false`     |
| `update_quantity` | `corrected_quantity` set, `status == "corrected"` | same + `review_actions` contains update_quantity   | `false`     |
| `update_sku`      | `position.sku` updated, `status == "corrected"`  | same + `review_actions` contains update_sku         | `false`     |
| `delete_position` | `status == "deleted"`                            | same + `review_actions` contains delete_position   | `false`     |

---

## Known limitations / deferred

- **Product selection when `product_id` is omitted**: Frontend often omits `product_id`; backend uses a single deterministic product per position. Multi-product positions remain a documented edge case.
- **Review history UI**: Backend stores `before_json`/`after_json`; the UI currently shows only action label and timestamp. Surfacing a concise change summary from before/after is deferred.
- **Consolidated/aggregated rows**: Manual correction semantics for SKU-level consolidated rows (multiple underlying positions) are not fully revalidated in this block.
