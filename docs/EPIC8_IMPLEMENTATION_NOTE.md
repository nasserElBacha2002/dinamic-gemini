# Épica 8 — Revisión manual — Implementation Note

## 1. Backlog interpretation for Épica 8

- **Goal:** First complete manual review workflow on top of persisted v3 result model.
- **In scope:** Reviewer can (1) confirm a position without changes, (2) correct quantity, (3) correct SKU/description, (4) logically delete a wrong position, (5) full auditability of every manual action.
- **HU-8.1:** Confirm position → create ReviewAction, position status → reviewed.
- **HU-8.2:** Correct quantity → set corrected_quantity, keep detected_quantity, position → corrected, audit.
- **HU-8.3:** Correct SKU/description → update product, position → corrected, audit.
- **HU-8.4:** Logical delete → position status → deleted, audit.
- **Out of scope (non-goals):** Multi-user assignment, bulk review, advanced moderation, websocket, broad UI redesign.

## 2. Current state summary

- **Domain:** `ReviewAction` and `ReviewActionType` exist in `src/domain/reviews/entities.py`. `Position` has `PositionStatus` (DETECTED, REVIEWED, CORRECTED, DELETED). `ProductRecord` has `corrected_quantity`, `sku`, `description`, `detected_quantity`.
- **Ports:** `ReviewActionRepository` with `save(review)`, `list_by_position(position_id)` in `src/application/ports/repositories.py`.
- **Persistence:** No `review_actions` table in `schema.sql`. Positions and product_records tables exist with status and corrected_quantity.
- **API:** v3 routes under `inventories_v3.py`; GET position detail returns position, products, evidences; no review endpoints.
- **Use cases:** `GetPositionDetailUseCase` exists; no review use cases.
- **Errors:** `PositionNotFoundError` exists; no `ProductNotFoundError` for product-not-found or product-not-in-position.
- **Frontend:** `PositionDetailPage` shows position summary, products, evidences; no review actions or history.

## 3. What Épica 7 already implemented

- Result persistence, result consultation, position list/detail APIs, frontend result views, position summary with sku/detected_quantity where available.

## 4. What is missing to complete manual review

- **Backend:** (1) `ProductNotFoundError` and validation that product belongs to position. (2) `review_actions` table and SQL + in-memory `ReviewActionRepository`. (3) Four use cases: ConfirmPosition, UpdateProductQuantity, UpdateProductSku, DeletePosition. (4) REST endpoint(s) for submitting review actions. (5) Include review_actions in position detail (or dedicated history endpoint). (6) Tests.
- **Frontend:** (1) API client and types for review actions and history. (2) Position detail page: confirm, update quantity, update SKU, delete; loading/error/success; refresh after action. (3) Simple review history display.

## 5. Target review action model for this epic

- **ReviewAction:** id, position_id, action_type (confirm | update_quantity | update_sku | delete_position), before_json, after_json, created_at, optional user_id, optional comment.
- **Persistence:** One row per action; position_id FK to positions(id); no FK to product (product_id can be stored in before_json/after_json when relevant).
- **ID:** Generated in use case (e.g. uuid4) when creating the entity before save.

## 6. Backend files to create

- `src/application/use_cases/confirm_position.py`
- `src/application/use_cases/update_product_quantity.py`
- `src/application/use_cases/update_product_sku.py`
- `src/application/use_cases/delete_position.py`
- `src/infrastructure/repositories/sql_review_action_repository.py`
- `src/infrastructure/repositories/memory_review_action_repository.py`
- `tests/application/use_cases/test_confirm_position.py` (and similar for other use cases)
- `tests/api/test_review_actions_api.py`

## 7. Backend files to modify

- `src/application/errors.py` — add ProductNotFoundError
- `src/database/schema.sql` — add review_actions table
- `src/application/use_cases/get_position_detail.py` — inject ReviewActionRepository, add review_actions to result
- `src/application/ports/` — no change (ReviewActionRepository already defined)
- `src/api/schemas/position_schemas.py` — add ReviewActionResponse, request body for POST review
- `src/api/routes/inventories_v3.py` — POST .../positions/{position_id}/reviews; extend GET position detail response with review_actions
- `src/api/dependencies.py` — get_review_action_repo, get_*_use_case for each review use case; extend get_get_position_detail_use_case with review_repo
- `src/runtime/v3_deps.py` — add get_review_action_repo

## 8. Frontend files to create

- None (all changes in existing files).

## 9. Frontend files to modify

- `frontend/src/api/types.ts` — ReviewActionSummary, review_actions in PositionDetailResponse, review request payload types
- `frontend/src/api/client.ts` — submitReviewAction(...)
- `frontend/src/pages/PositionDetailPage.tsx` — confirm button, quantity/SKU forms, delete button, refresh on success, review history section

## 10. Backend design summary

- **Single endpoint:** `POST /api/v3/inventories/{inv}/aisles/{aisle}/positions/{pos}/reviews` with body discriminated by `action_type`: confirm (no extra fields), update_quantity (product_id, corrected_quantity), update_sku (product_id, sku, description?), delete_position (no extra fields). Validation per action type; 404 for missing position/product; 422 when product does not belong to position.
- **Use cases:** Each use case validates inventory/aisle/position (and product when needed), updates domain entities, saves position/product, creates and saves ReviewAction with before_json/after_json. ConfirmPosition: position.status = REVIEWED. UpdateQuantity/UpdateSku: product save + position.status = CORRECTED. DeletePosition: position.status = DELETED (no product changes).
- **Detail:** GetPositionDetailUseCase will call review_repo.list_by_position and include in result; API response and schema include review_actions list.

## 11. Frontend design summary

- **Actions:** Confirm (button); per-product “Correct quantity” / “Correct SKU” (inline form or small dialog); “Delete position” (button + confirm dialog). Each action calls submitReviewAction, then refetches position detail (load()).
- **State:** Local loading/success/error per action (e.g. confirmLoading, quantityError) to avoid duplicate toasts and allow targeted feedback.
- **History:** If backend returns review_actions in detail, show a simple list (action_type, before/after summary, created_at).

## 12. Risks / decisions

- **Decision:** One POST endpoint with action_type + optional fields instead of four separate endpoints; aligns with current v3 style and keeps route count low.
- **Risk:** Frontend form validation (e.g. corrected_quantity integer ≥ 0) should match backend; backend validates and returns 422.
- **Decision:** Include review_actions in existing GET position detail response rather than a separate GET .../reviews endpoint to keep detail page simple and avoid extra round-trip.
