# Release 3.2.5 — Phase 6: Review Operational Consistency

## Scope

This document defines the operator-facing operational contract for manual review/corrections in v3:

- what each review action changes,
- what is persisted,
- what must be visible after reread (list + detail),
- how corrected state relates to review history,
- evidence hierarchy and count-origin visibility,
- and which limitations are deferred.

---

## 1. Operator-facing review model

- **Review status**: Derived from position `status` + `needs_review`. NEEDS_REVIEW when `needs_review === true` and `status === "detected"`; CONFIRMED when status is reviewed or corrected; INVALID when status is deleted.
- **Why in review**: The backend exposes only a boolean `needs_review`. The pipeline sets it from entity signals (e.g. count_status NEEDS_REVIEW, NOT_COUNTABLE, low confidence). A dedicated “review reason” field is **not** exposed in this release; the operator can use status, qtySource, traceability, and confidence together to infer context. **Deferred**: stable needsReviewReason enum when backend supports it.
- **Current final state**: The visible quantity is always `corrected_quantity ?? qty` (see `docs/3.2.5/POSITION_RESULT_CONTRACT.md`). Current visible SKU comes from position (derived from detected_summary_json.internal_code / product). After any successful manual action, `needs_review` is set to false so the case no longer appears “in review” for filters/KPIs.

---

## 2. Review reason model (current limits)

- The API does **not** expose a dedicated `needsReviewReason` or equivalent.
- Operators can infer context from: `needs_review`, `status`, `qtySource`, `qtyInferenceReason` (when inferred), `traceability_status`, `confidence`, and evidence availability.
- **Deferred**: Explicit review-reason enum or field when the backend can expose a stable, non-heuristic basis.

---

## 3. Count-origin visibility model

- **qtySource**: Provenance of the **system** quantity `qty`: `detected` | `inferred` | `consolidated`. The UI shows this so the operator knows where the system count came from.
- **qtyInferenceReason**: When `qtySource === "inferred"`, this may contain a short reason; the UI displays it when present.
- **Final visible quantity**: When `corrected_quantity != null`, the visible quantity is the operator override; when null, it is the system `qty`. The UI shows “Current quantity” and, when overridden, “System quantity” (the pre-override system value).

---

## 4. Current final-state visibility model

- **Current quantity**: Always `corrected_quantity ?? qty`. Displayed prominently on the result detail summary card.
- **System quantity**: When `corrected_quantity` is set, the backend `qty` (system-resolved quantity before override) is shown so the operator sees what was overridden.
- **Count origin**: One line showing Detected / Inferred / Consolidated (and inference reason when applicable).
- **Review status**: Chip showing Needs review / Confirmed / Invalid (and traceability/confidence as already present).

---

## 5. Evidence hierarchy rules

- **Primary evidence**: Exactly one evidence per position can be primary (`is_primary === true`). The UI labels it “Primary evidence” (source image when available, or “Primary evidence recorded” when only metadata exists).
- **Supporting evidence**: All other evidences are supporting. The UI labels them “Supporting evidence” with count when present.

---

## 6. Supported manual actions and unsupported/deferred

**Supported (backend and UI):**

| Product term | Backend action    | Semantics |
|-------------|-------------------|-----------|
| Approve     | `confirm`         | Accept result as correct without changing quantity or SKU. Sets status to reviewed. |
| Edit quantity | `update_quantity` | Set corrected (manual) quantity. Replaces system count for this result. |
| Override SKU | `update_sku`      | Override SKU/classification (and optional description). Visible SKU updated on reread. |
| Reject / invalidate | `delete_position` | Mark result as invalid/deleted. No further review actions available. |

**Unsupported / deferred:**

- **Reclassify** (beyond SKU): No separate “reclassify” action; use `update_sku` for SKU/classification override. Broader reclassification is deferred.
- **Multi-step approval**: No approval chains or role-based approval; single operator action only.
- **Bulk actions**: Not in scope; one position per request.

---

## 7. Action-to-persistence mapping

- **confirm**: PositionRepository.save(position with status=reviewed, needs_review=false), ReviewActionRepository.save(review with before/after status).
- **update_quantity**: ProductRecordRepository.save(product with corrected_quantity), PositionRepository.save(position with status=corrected, needs_review=false), ReviewActionRepository.save(review with before/after corrected_quantity).
- **update_sku**: ProductRecordRepository.save(product with sku/description), PositionRepository.save(position with detected_summary_json.internal_code updated, status=corrected, needs_review=false), ReviewActionRepository.save(review with before/after sku/description).
- **delete_position**: PositionRepository.save(position with status=deleted, needs_review=false), ReviewActionRepository.save(review with before/after status).

Each review record stores: action_type, before_json, after_json, created_at, optional user_id and comment.

---

## 8. Action-to-reread guarantees

After a successful POST to the review endpoint:

- **List** (`GET .../positions`): The updated position appears with the same status, corrected_quantity, sku (for update_sku), and needs_review false.
- **Detail** (`GET .../positions/{id}`): Same position fields; evidences unchanged; review_actions includes the new action with before_json and after_json.
- **Current final state**: Visible quantity = corrected_quantity ?? qty; visible SKU from position; review status chip reflects reviewed/corrected/deleted.
- **Audit**: Review history shows the new entry with a concise change summary (e.g. “Quantity: 3 → 5”, “SKU: ABC → XYZ”, “Status: detected → reviewed”) when before/after are available.

---

## 9. Basic audit model

- **Persisted**: Each review action stores id, position_id, action_type, before_json, after_json, created_at, user_id (optional), comment (optional).
- **before_json / after_json**: Sufficient to trace what changed (e.g. status, corrected_quantity, sku, description). The UI surfaces a concise, human-readable summary (e.g. “Quantity: 3 → 5”, “Status: detected → reviewed”) for known action types; raw JSON is not shown by default.
- **Operational use**: Operators and support can see what action was performed and what the previous and new values were; the detail history section shows the change summary when available.

---

## 10. Implementation notes (Phase 6)

- **Backend**: needs_review is set to false after every successful confirm, update_quantity, update_sku, and delete_position. update_sku updates position.detected_summary_json.internal_code so list/detail reread shows the new SKU.
- **Frontend**: Result detail shows Current quantity, System quantity (when override exists), Count origin (qtySource + qtyInferenceReason). Evidence is labeled Primary / Supporting. Review actions have short descriptions of effect. Review history shows a human-readable change summary from before_json/after_json when available.
- **Tests**: test_review_actions_api.py validates list/detail reread and needs_review for all four actions.

---

## 11. Known limitations / deferred

- **Review reason**: No explicit needsReviewReason in API; operator infers from status, qtySource, traceability, confidence.
- **Product selection**: When product_id is omitted, backend uses single deterministic product; multi-product positions are edge case.
- **Consolidated rows**: Manual correction semantics for SKU-level consolidated rows (multiple underlying positions) are not fully revalidated in this block.
- **Full forensic audit**: Raw before/after JSON is available in the API for support; the UI shows only a concise summary. Full audit explorer is deferred.
