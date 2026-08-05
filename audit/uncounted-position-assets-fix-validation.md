# Uncounted position assets fix — validation

**Date:** 2026-08-05  
**Task:** Exclude positioning-label images from “Imágenes sin contar”  
**Final status:** `CORRECTIONS_WITH_WARNINGS`

## Root cause

`ListJobImageResults` / coverage SQL defined `without_result` as **no linked product position**, with no knowledge of `image_position_label_detections`.

Position-label photos (e.g. `LEGACY_UNSIGNED_REQUIRES_REVIEW`) correctly appear in the positioning sequence but have zero product results → they were listed as uncounted with “Agregar resultado”.

## Condition before

```
without_result ⇔ NOT has_product_result_link(asset)
```

No join/filter on position-label detections. Pagination/counters used the same predicate.

## Condition after

1. Load job position-label detections.
2. Reduce per asset via `reduce_asset_detections` (existing classifier).
3. Assets with event kind ∈ `{POSITION_LABEL_RESOLVED, POSITION_LABEL_UNRESOLVED, POSITION_TRANSITION_APPLIED}` → `exclude_source_asset_ids`.
4. Apply exclusion **before** `without_result` count and pagination (SQL + memory repos).
5. Response rows include: `operational_role`, `is_product_candidate`, `excluded_from_uncounted`, `uncounted_reason`.

Filename is never used.

## Backend ↔ frontend contract

| Field | Meaning |
|-------|---------|
| `operational_role` | `PRODUCT_IMAGE` / `PRODUCT_WITHOUT_RESULT` path via classifier roles / `POSITION_LABEL_*` / `NO_POSITION_SYMBOL` / `UNKNOWN` |
| `is_product_candidate` | May receive manual product result |
| `excluded_from_uncounted` | Must not appear in unmatched queue |
| `uncounted_reason` | Exclusion motive enum value |
| `counters.without_result` | Product candidates without result only |
| `counters.total_images` | All primary photos (unchanged semantics) |

Frontend uses backend counters for the tab; defensive filter + hide “Agregar resultado” when `is_product_candidate === false`.

## Counters evidence (nine-asset case)

| Metric | Before (bug) | After |
|--------|--------------|-------|
| total_images | 9 | 9 |
| with_result | 7 | 7 |
| without_result | 2 (pasillo photos) | **0** |
| without_result items | 2 | **[]** |

## Files modified (this fix)

- `backend/src/application/services/job_image_coverage/asset_operational_role.py` (new)
- `backend/src/application/use_cases/positions/list_job_image_results.py`
- `backend/src/application/ports/job_image_coverage_repository.py`
- `backend/src/infrastructure/persistence/sql_job_image_coverage_repository.py`
- `backend/src/infrastructure/persistence/memory_job_image_coverage_repository.py`
- `backend/src/api/schemas/image_result_schemas.py`
- `backend/src/api/routes/v3/image_results.py`
- `backend/src/api/dependencies.py`
- `backend/tests/unit/job_image_coverage/test_asset_operational_role.py`
- `backend/tests/api/test_job_image_results.py`
- `frontend/src/api/types/responses.ts`
- `frontend/src/features/results/components/imageCoverage/JobImageResultsGrid.tsx`
- `frontend/src/features/results/components/imageCoverage/JobImageResultCard.tsx`
- frontend imageCoverage tests

## Validation commands

### Backend

```bash
.venv/bin/pytest backend/tests/unit/job_image_coverage/ backend/tests/api/test_job_image_results.py -q
```

- Exit: **0** — **22 passed**

```bash
cd backend && ../.venv/bin/ruff check … && ../.venv/bin/black --check … && ../.venv/bin/mypy …
```

- Exit: **0**

### Frontend

```bash
npm run typecheck   # 0
npm run lint        # 0 errors (22 pre-existing warnings)
npm run test -- --run tests/features/results/imageCoverage/JobImageResultsGrid.test.tsx \
  tests/features/results/imageCoverage/JobImageResultCard.test.tsx
# 6 passed
npm run build       # 0
```

## Residual risks

- Working tree still contains **prior uncommitted P1 positioning-semantics** changes (not part of this fix list) — review/diff artifacts cover the full tree.
- Direct `POST …/manual-result` on a position-label asset is not newly blocked server-side (list + UI hide the action). Follow-up: reject in `CreateManualImageResultUseCase` using the same classifier.
- P2 association algorithm unchanged.

## Explicit non-goals confirmed

- No product results fabricated for position photos.
- Sequence / detections unchanged.
- No filename heuristics.
- P2 not implemented.
