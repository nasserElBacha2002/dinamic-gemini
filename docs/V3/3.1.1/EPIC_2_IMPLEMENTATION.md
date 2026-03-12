# Epic 2 — Backend and data-contract support for Result-centric review flow

## Scope implemented

- **Strategy:** Option C — Add explicit result-aligned response fields while keeping legacy fields. No route or URL changes.
- **Backend:** Position list and detail responses now expose `has_evidence` and `source_image_original_filename` at top level. Pipeline persists `source_image_original_filename` in `detected_summary_json` for new runs.
- **Frontend:** PositionSummary type and mappers updated to consume the new fields; mapper prefers API `has_evidence` when present.

---

## Files changed

### Backend

| Path | Change |
|------|--------|
| `src/api/schemas/position_schemas.py` | Added `has_evidence: bool = False` and `source_image_original_filename: Optional[str] = None` to `PositionSummaryResponse`. |
| `src/infrastructure/pipeline/v3_report_mapper.py` | In `_detected_summary()`, persist `source_image_original_filename` from report entity when present. |
| `src/api/routes/inventories_v3.py` | `_enrich_position_traceability_from_report()` now returns `(sid, ts, source_image_original_filename)` and is used as fallback when summary lacks it. `_position_to_summary()` sets `has_evidence` from `primary_evidence_id` and `source_image_original_filename` from summary or report. |

### Frontend

| Path | Change |
|------|--------|
| `frontend/src/api/types/responses.ts` | Added optional `has_evidence?: boolean` to `PositionSummary`. |
| `frontend/src/features/results/mappers/positionToResult.ts` | `mapPositionSummaryToResultSummary()` uses `p.has_evidence ?? derived` so API value is preferred when present. |

### Tests

| Path | Change |
|------|--------|
| `tests/api/test_position_summary_mapping.py` | Assertions for `has_evidence` and `source_image_original_filename`; new tests for Epic 2 fields. |
| `frontend/tests/resultMappers.test.ts` | New test: prefers API `has_evidence` when present. |

---

## Contract alignment with ResultSummary

- **has_evidence:** Backend sends explicit boolean; frontend no longer infers only from `primary_evidence_id`. Backward compatible: frontend still derives when field is absent.
- **source_image_original_filename:** Backend sends when available (from `detected_summary_json` or from `hybrid_report.json` fallback). Detail and list both use the same position summary shape, so detail benefits as well.
- **Existing fields:** `sku`, `detected_quantity`, `source_image_id`, `traceability_status` unchanged. `detected_summary_json` still present for compatibility.

---

## Verification

- Frontend: `npm run typecheck` and `npm run test` (70 tests, including 24 in resultMappers) pass.
- Backend: run `pytest tests/api/test_position_summary_mapping.py` to confirm position summary mapping and new Epic 2 fields.

---

## Ready for Epic 3

- List and detail responses are better aligned with the frontend ResultSummary/ResultDetail model.
- Less reliance on inferring `has_evidence` from `primary_evidence_id` or reading `source_image_original_filename` only from `detected_summary_json`; backend exposes them at top level when available.
- No breaking changes: legacy fields retained; new fields additive.
