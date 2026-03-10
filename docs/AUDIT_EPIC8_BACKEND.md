# Backend Audit — Épica 8 Review Workflow

## 1. Executive verdict

**READY WITH MINOR FIXES**

The Épica 8 backend is architecturally sound, respects the intended layering (api → application/use_cases → ports → infrastructure), and delivers a complete manual review workflow with auditability. Use cases are framework-agnostic, validation is centralized in a small helper module, and the route layer is thin with clear exception mapping. No critical or high-severity defects were found that would block the next stage. A few medium/low items (test gaps, optional consistency tweaks, and one product decision on acting on deleted positions) should be addressed or explicitly deferred.

---

## 2. What is correct

- **Architecture and dependency direction**
  - Routes depend only on use cases and application errors; no infrastructure types in route code.
  - Use cases depend on ports (repositories, clock); `review_validation` lives in application and is used only by review use cases.
  - `v3_deps` and `api.dependencies` wire repositories and use cases correctly; `ReviewActionRepository` follows the same SQL-with-in-memory-fallback pattern as other v3 repos.

- **Use-case quality**
  - Each review use case has a single responsibility (confirm, update quantity, update SKU, delete). Status transitions are correct: `REVIEWED` for confirm, `CORRECTED` for quantity/SKU, `DELETED` for delete.
  - Duplication is reduced via `review_validation.resolve_position` and `resolve_product_for_position`; use cases stay short and readable.
  - Application exceptions (`InventoryNotFoundError`, `AisleNotFoundError`, `PositionNotFoundError`, `ProductNotFoundError`, `ValueError`) are used consistently and mapped in one place in the API.

- **API layer**
  - `submit_review_action` is a simple dispatch; per-action logic lives in `_handle_confirm`, `_handle_update_quantity`, `_handle_update_sku`, `_handle_delete_position`. `_review_exception_to_http` centralizes exception → HTTP mapping.
  - `ReviewActionRequest.action_type` is a Pydantic `Literal["confirm", "update_quantity", "update_sku", "delete_position"]`, so invalid values are rejected at validation with 422.
  - Position detail response includes `review_actions` with `Field(default_factory=list)`; schema is safe and aligned with domain.

- **Persistence and audit**
  - Every successful review action creates a `ReviewAction` with `before_json`/`after_json` and `created_at` before saving position/product. Audit is written after entity updates, so a failed save would not leave orphan audit rows.
  - SQL and memory repos both return `list_by_position` ordered by `(created_at ASC, id ASC)`. Invalid JSON in SQL is logged with a warning and falls back to `{}`.
  - Domain `ReviewAction` and `ReviewActionType` match the schema and API; `review_actions` table and port contract are aligned.

- **Tests**
  - Use-case tests cover success and not-found/mismatch paths for confirm, update_quantity, update_sku, delete. Audit persistence (e.g. `review_repo.list_by_position`, `before_json`/`after_json`) is asserted.
  - API tests use dependency overrides to seed repos and cover confirm, update_quantity, delete, invalid action_type, missing product_id, position not found, and GET detail including `review_actions`. Memory repo ordering has a dedicated test.

---

## 3. Issues found

### Critical

- **None.**

### High

- **None.**

### Medium

- **No API-level test for `update_sku` success path.**  
  - **What:** `test_post_review_update_quantity_returns_204_and_detail_updated` and delete/confirm are covered; there is no equivalent test for `action_type: "update_sku"` with `product_id`, `sku`, and optional `description` returning 204 and detail showing updated SKU and review_actions.  
  - **Why it matters:** Regressions in the update_sku handler or schema could go unnoticed.  
  - **Recommendation:** Add an API test that POSTs `update_sku` with valid body and asserts 204, then GET detail and asserts `position.status == "corrected"`, product `sku`/`description` updated, and one review_action with `action_type == "update_sku"`.

- **No API-level test for 404 when product does not belong to position.**  
  - **What:** Update_quantity and update_sku use cases raise `ProductNotFoundError` when product is missing or has a different `position_id`. API tests do not assert that the route returns 404 for a valid but wrong `product_id`.  
  - **Why it matters:** Ensures the route correctly maps `ProductNotFoundError` to 404 for product-scoped actions.  
  - **Recommendation:** Add a test that POSTs `update_quantity` (or `update_sku`) with a `product_id` that either does not exist or belongs to another position and assert 404 and appropriate detail.

- **No explicit guard against acting on an already-deleted position.**  
  - **What:** Confirm, update_quantity, and update_sku do not check `position.status == PositionStatus.DELETED`. A caller can e.g. confirm or correct quantity on a deleted position, which would set status back to REVIEWED or CORRECTED and append a ReviewAction.  
  - **Why it matters:** Business rule ambiguity: should review actions be allowed on deleted positions? If not, current behavior is wrong; if yes, it may be intentional (e.g. “un-delete” or re-review).  
  - **Recommendation:** Decide product rule. If actions on deleted positions are disallowed: add a check after `resolve_position` (and optionally in `resolve_product_for_position` when position is deleted) and raise a dedicated error (e.g. `PositionDeletedError`) mapped to 409 or 422. If allowed, document it in the use case or backlog.

### Low

- **GetPositionDetailUseCase does not use `review_validation.resolve_position`.**  
  - **What:** Position detail use case inlines the same inventory/aisle/position resolution as the review use cases instead of calling `resolve_position`.  
  - **Why it matters:** Small duplication and risk of drift if resolution rules change.  
  - **Recommendation:** (Deferrable.) Refactor `GetPositionDetailUseCase.execute` to call `resolve_position(...)` then load products, evidences, and review_actions. Reduces duplication and keeps resolution semantics in one place.

- **Route handlers catch `ProductNotFoundError` for confirm and delete.**  
  - **What:** `_handle_confirm` and `_handle_delete_position` include `ProductNotFoundError` in their `except` tuple, but those use cases never raise it.  
  - **Why it matters:** Dead code; no functional bug, but slightly misleading.  
  - **Recommendation:** Remove `ProductNotFoundError` from the except tuple in `_handle_confirm` and `_handle_delete_position` for clarity.

- **Unreachable fallback in `submit_review_action`.**  
  - **What:** The final `raise HTTPException(status_code=422, detail="Invalid action_type")` is unreachable when `action_type` is a Literal validated by Pydantic.  
  - **Why it matters:** Defensive only; no runtime impact.  
  - **Recommendation:** Keep as defensive fallback or remove and rely on Pydantic; either is acceptable.

---

## 4. Architecture assessment

The manual review backend keeps the intended structure:

- **api** — Routes only parse request, call use cases or private handlers, map exceptions to HTTP, and build responses. No business rules in the route module. Dependencies are injected via FastAPI `Depends`; no infrastructure imports in routes beyond what is needed for response DTOs and application errors.
- **application/use_cases** — Review use cases orchestrate validation (via `review_validation`), domain updates, and persistence. They depend only on ports (repositories, clock). `review_validation` is a small, focused module used only by the four review use cases; it does not introduce a heavy shared service.
- **ports** — `ReviewActionRepository` is defined in `application.ports.repositories` and used by review use cases and GetPositionDetail. No new ports were added in the wrong layer.
- **infrastructure** — SQL and in-memory implementations of `ReviewActionRepository` live under `infrastructure.repositories` and are wired in `v3_deps` with the same pattern as other v3 repos.

The only minor inconsistency is `GetPositionDetailUseCase` still inlining inv/aisle/position resolution instead of using `resolve_position`; that is a low-priority consistency improvement, not an architectural violation.

---

## 5. Use-case/API assessment

**Use cases:** Cohesive and correctly scoped. Each use case performs one review action, updates the right entities (position and optionally product), and persists a single `ReviewAction` with consistent before/after payloads. Validation is centralized in `review_validation`, so adding a new review action type would require a new use case and a new branch in the route, without duplicating resolution logic. Application exceptions are used consistently; no framework types leak into use cases.

**API:** `submit_review_action` is maintainable: a short dispatch on `body.action_type` to four handlers. Each handler validates its payload (product_id, corrected_quantity, sku), calls the corresponding use case, and maps exceptions via `_review_exception_to_http`. Validation and error mapping are consistent. Review history is exposed in GET position detail via `review_actions`; the response schema and default are correct. `ReviewActionRequest.action_type` is strongly typed with Literal, so invalid values are rejected at the schema layer.

---

## 6. Persistence/audit assessment

**Persistence:** `review_actions` table matches the domain (id, position_id, action_type, before_json, after_json, created_at, user_id, comment). FK to `positions(id)` is correct. Repositories only insert review rows (no update), which matches the append-only audit model. SQL repo uses parameterized queries; in-memory repo keeps a list and filters by position_id with explicit sort by (created_at, id). Ordering is consistent between adapters.

**Audit:** Every successful execution of a review use case creates exactly one `ReviewAction` after updating position (and product when applicable). before_json/after_json content matches the backlog (status for confirm/delete; product_id and corrected_quantity for update_quantity; product_id, sku, description for update_sku). Invalid JSON in the SQL layer is logged and fallback to `{}` keeps the repository resilient without hiding data issues. Missing position/product or hierarchy mismatches raise application exceptions and are mapped to 404; no silent wrong-state updates were found.

---

## 7. Test assessment

**Strengths:** Use-case tests cover success and failure paths (not found, wrong aisle, wrong position, wrong product) for all four review use cases and assert both entity updates and audit record creation. API tests use dependency overrides to avoid hitting a real DB and cover confirm, update_quantity, delete, invalid action_type, missing product_id, position not found, and GET detail with `review_actions`. Memory repo ordering is tested explicitly.

**Gaps:**
- No API test for **update_sku** success (204 + detail with updated sku/description and review_actions).
- No API test for **404 when product_id is wrong** (wrong or non-existent product for update_quantity/update_sku).
- No test that **multiple review actions** on the same position appear in correct order in GET detail (ordering is tested at repo level only).
- **SqlReviewActionRepository** is not tested (e.g. invalid JSON warning, ordering); acceptable for this stage if SQL is covered by integration/e2e elsewhere.

Overall, tests are sufficient to trust the current contract and error handling; the gaps above are recommended additions rather than blockers.

---

## 8. Blocking fixes before continuing

- **None.** The implementation is suitable as a base for the next stage. Addressing the two medium test gaps and the product decision on deleted positions is recommended but not blocking.

---

## 9. Deferrable improvements

1. Add API test for **update_sku** success (POST then GET detail, assert status, product sku/description, review_actions).
2. Add API test for **404 on wrong product_id** for update_quantity or update_sku.
3. Decide product rule for **review actions on deleted positions**; if disallowed, add guard and map to 409/422.
4. Refactor **GetPositionDetailUseCase** to use `resolve_position` for consistency with review use cases.
5. Remove **ProductNotFoundError** from except tuples in `_handle_confirm` and `_handle_delete_position` (dead code).
6. Optionally add an integration or repository-level test for **SqlReviewActionRepository** (invalid JSON logging, ordering) if SQL path is not covered elsewhere.

---

## 10. Final recommendation

**Proceed with the implementation and plan the minor fixes.**

- Treat the current Épica 8 backend as **ready for the next stage** (e.g. Épica 9 or follow-up features).
- Schedule the two medium-priority tests (update_sku API success, 404 for wrong product_id) and the product decision on deleted positions in the next sprint or backlog.
- Apply the low-priority/deferrable items (GetPositionDetail + resolve_position, exception list cleanup) when touching those modules for other reasons.

No blocking issues were identified; the review workflow is architecturally correct, auditable, and maintainable.
