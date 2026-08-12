# Implementation validation — Operator position merge (SKU/results)

**Date:** 2026-08-12  
**Status:** IMPLEMENTED_AND_VALIDATED (core path)  
**Task:** Merge selected aisle position results with mandatory preview

## 1. Architecture found

- Operator-visible aisle results are **Position** rows (+ ProductRecord), listed with `consolidate_by_sku: false` on the UI.
- Existing **aisle label merge** (`POST …/aisles/{id}/merge`) consolidates RawLabel → NormalizedLabel → FinalCount — **not** this feature.
- Projection-time SKU consolidation (`position_sku_consolidation.py`) is separate and remains non-persisted SoT.

## 2. Canonical product identity

- **`canonicalize_sku(ProductRecord.sku)`**, fallback **`canonicalize_sku(detected_summary_json.internal_code)`**.
- Display SKU / EAN / `position_barcode` are **not** used as identity.
- Shared helper: `backend/src/application/services/position_operator_merge.py`.

## 3. Quantity rule

- Each position row’s **final display quantity** (operator `corrected_quantity` when set, else system qty from product/summary) is treated as independent counted units.
- Merged quantity = **sum** of source final display quantities (e.g. 4+3+2=9).
- Server recalculates on confirm; client never sends quantity as SoT.

## 4. Persistence model

- Migration **0097**: `positions.merged_into_position_id`, `positions.merged_at`.
- Sources are **not** hard-deleted; marked with `merged_into_position_id` + `review_resolution=merged`.
- Survivor keeps evidence; summary gets `final_quantity` + `aggregated_from_ids`.
- Default `list_by_aisle` / exports / review queue hide merged sources.

## 5–6. Endpoints

- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge/preview`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge`  
  Body: `{ result_ids, preview_token }` — server reloads + revalidates + recalculates.

## 7. Validations

- ≥2 unique IDs; no duplicates; all exist in aisle; inventory soft-deleted blocked; deleted/already-merged blocked; SKU identity mismatch; declared position-code mismatch.

## 8–9. Concurrency / idempotency

- `preview_token` = SHA-256 of `id:updated_at` set; stale token → 409 `PositionMergeStalePreviewError`.
- Confirm retry when sources already merged into the included survivor → `already_merged: true`.
- SQL confirm uses transactional UoW (`SqlPositionMergeUnitOfWork`).

## 10. Conflicts

- Blocking: sku_mismatch, missing identity, position_code_mismatch, already_merged, deleted, aisle mismatch.
- Warnings: description/job/barcode/image differences (shown in preview).

## 11. Frontend

- Aisle results: row checkboxes, “Fusionar seleccionados”, preview dialog ANTES→DESPUÉS, confirm/cancel, clear selection, invalidate positions query.

## 12. Mobile

- Mobile **merge-results** path is aisle **label** merge, not position list.
- Position lists/exports now exclude `merged_into_*` sources → no double-count of source+survivor for CSV/ZIP/collector paths updated.
- Mobile apps consuming raw unfiltered position dumps would need the same filter; documented as follow-up if a dedicated mobile positions API lacks the filter.

## 13. Exports

- `append_inventory_csv_rows_for_aisle` and `ExportInventoryCollector` exclude merged sources.

## 14. Migrations

- `0097_positions_merge.sql` / `.down.sql`; mirrored in `schema.sql`.

## 15. Tests added

- `backend/tests/application/use_cases/test_merge_positions.py` (11 cases)
- `frontend/tests/PositionMergePreviewDialog.test.tsx` (2 cases)

## 16–17. Commands executed

```bash
backend/.venv/bin/python -m pytest tests/application/use_cases/test_merge_positions.py -q --no-cov
# → 11 passed

backend/.venv/bin/ruff check …merge-related files
# → All checks passed

cd frontend && npm test -- --run tests/PositionMergePreviewDialog.test.tsx
# → 2 passed
```

## 18. Risks / follow-ups

- Broader analytics aggregations that use `list_by_aisles` without filtering merged sources may still count sources until those call sites are audited.
- Concurrent cross-set merges (overlapping IDs) rely on stale token / already_merged checks; no DB unique constraint on merge set.
- Expanding frontend table selection tests for AislePositionsPage is recommended beyond the dialog unit tests.
