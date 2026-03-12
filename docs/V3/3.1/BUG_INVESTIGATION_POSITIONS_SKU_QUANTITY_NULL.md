# Bug Investigation: Positions list returns `sku: null` and `detected_quantity: null`

## Symptom

The **Aisle results — Positions** table (frontend) receives a positions list where:

- `sku` is `null`
- `detected_quantity` is `null`

even though `detected_summary_json` on the same positions contains fields such as `internal_code`, `final_quantity`, `product_label_quantity`, `count_status`, `pallet_id`. The flattened top-level `sku` and `detected_quantity` remain null.

## Expected Behavior

For the positions list API, the frontend expects:

- **`sku`**: A display value for the position (product/SKU or fallback identifier) when available.
- **`detected_quantity`**: A numeric count when the pipeline has resolved or provided a quantity.

When the pipeline has provided data (e.g. in `detected_summary_json`), these fields should be populated when possible; when not, null is acceptable but should be a conscious outcome of business rules, not a mapping bug.

## Area(s) Suspect (Platform / Pipeline)

- **Platform:** API response builder (`_position_to_summary`, `_summary_sku_and_quantity_from_position`), v3 report mapper (`_detected_summary`), persistence of `detected_summary_json`.
- **Pipeline:** Report entity shape (`internal_code`, `final_quantity`, `product_label_quantity`), decision layer (`assign_count_status` setting `final_quantity = None` for NEEDS_REVIEW / NOT_COUNTABLE).

## Hypotheses (ranked)

### H1: Upstream data has nulls; API correctly reflects them (not a transformation bug)

- **Why likely:** User states that in the sample payload, `internal_code`, `final_quantity`, and `product_label_quantity` are **null** in the shown examples, and `count_status` is often `NEEDS_REVIEW` or `NOT_COUNTABLE`. The decision layer explicitly sets `final_quantity = None` for NEEDS_REVIEW and NOT_COUNTABLE. The list API derives `sku` only from `internal_code` and `detected_quantity` from `final_quantity` then `product_label_quantity`; if all are null, the API correctly returns null.
- **How to confirm:** Log or inspect one full position from the list response: `detected_summary_json.internal_code`, `detected_summary_json.final_quantity`, `detected_summary_json.product_label_quantity`. If they are all null/absent, the transformation is correct.
- **Logs/metrics to add:** For list response (or in use case): log per position `(internal_code is None, final_quantity is None, product_label_quantity is None, count_status)` for a sample.
- **Minimal repro:** Run pipeline for an aisle where the model returns NEEDS_REVIEW/NOT_COUNTABLE and does not set internal_code/product_label_quantity; persist; call GET positions. Expect sku/detected_quantity null.
- **Fix (minimal):** None if behavior is intentional. If product wants a display value when internal_code is missing, add fallback (see H2).

### H2: No fallback for `sku` when `internal_code` is null (mapping gap)

- **Why likely:** The list API derives `sku` **only** from `detected_summary_json.internal_code`. The v3 report mapper stores in `detected_summary_json` only: `entity_uid`, `entity_type`, `pallet_id`, `internal_code`, `final_quantity`, `product_label_quantity`, `count_status`, plus traceability. It does **not** store `position_barcode` or `review_display_label`, which the report does have. So when `internal_code` is null, the list builder has no alternative to show (e.g. pallet/position id) and returns `sku: null`.
- **How to confirm:** Check `_detected_summary` in `v3_report_mapper.py`: it does not copy `position_barcode` or `review_display_label`. Check `_summary_sku_and_quantity_from_position` in `inventories_v3.py`: it only uses `j.get("internal_code")` for sku.
- **Logs/metrics to add:** Count positions where `internal_code` is null but report entity had `position_barcode` or `review_display_label` (would require one-time trace in mapper).
- **Minimal repro:** Create a report entity with `internal_code: null`, `position_barcode: "P-001"`; persist; GET positions; observe sku null. Then add fallback (H2 fix) and confirm sku shows "P-001".
- **Fix (minimal):** (1) In `v3_report_mapper._detected_summary`, add `position_barcode` and/or `review_display_label` from the report entity into the summary dict. (2) In `_summary_sku_and_quantity_from_position`, use `internal_code` then fallback to `review_display_label` or `position_barcode` (after normalizing empty string to None) for the derived `sku`. Align with `derive_review_display_label` semantics (internal_code else position_barcode).

### H3: Persistence drops or corrupts `detected_summary_json` (persistence issue)

- **Why less likely:** SQL repo saves `detected_summary_json` as JSON and loads it back; the list response includes `detected_summary_json` with the same keys (internal_code, final_quantity, etc.). If the user sees those keys in the response, the JSON was persisted and loaded.
- **How to confirm:** Compare one position’s `detected_summary_json` in DB (e.g. raw column) with the same position’s `detected_summary_json` in the API response; they should match.
- **Logs/metrics to add:** None unless H1/H2 are ruled out.
- **Minimal repro:** Persist a position with non-null internal_code/final_quantity; load by list; assert response.sku and response.detected_quantity are set.
- **Fix (minimal):** N/A unless evidence shows corruption (e.g. wrong column, encoding).

### H4: Wrong key names (report vs mapper vs response)

- **Why unlikely:** Report builder uses `internal_code`, `final_quantity`, `product_label_quantity`; mapper uses `entity.get("internal_code")` etc.; response builder uses `j.get("internal_code")`, `j.get("final_quantity")`, `j.get("product_label_quantity")`. Key names are consistent.
- **How to confirm:** Grep report build, mapper, and list builder for these keys; confirm they match.
- **Fix (minimal):** N/A unless a typo is found.

## Most Likely Root Cause

**Combination of:**

1. **Upstream (pipeline/decision):** For entities with `count_status` NEEDS_REVIEW or NOT_COUNTABLE, `assign_count_status` sets `final_quantity = None`. The report then has `final_quantity: null`. If the model also did not return `internal_code` or `product_label_quantity`, those are null in the report and in `detected_summary_json`. So **detected_quantity and sku being null are the correct consequence of upstream nulls** for those entities.

2. **Mapping gap (optional improvement):** When `internal_code` is null, the list API has no fallback (e.g. `position_barcode` or `review_display_label`) because the mapper does not store them in `detected_summary_json`. So **sku is null whenever internal_code is missing**, even when the report had a position/pallet identifier that could be shown.

So: **not a bug in the sense of wrong mapping or lost data**; the transformation from `detected_summary_json` to `sku` and `detected_quantity` is correct. The nulls are either (a) intentional for NEEDS_REVIEW/NOT_COUNTABLE when no quantity is resolved, or (b) a product/UX gap because we do not expose a fallback label when `internal_code` is missing.

## Exact Failing Code Path (where nulls come from)

- **Route:** `GET /api/v3/inventories/{id}/aisles/{aid}/positions` → `list_aisle_positions()` in `src/api/routes/inventories_v3.py`.
- **Use case:** `ListAislePositionsUseCase.execute()` → `position_repo.list_by_aisle(aisle_id)` → returns `Sequence[Position]`.
- **Response builder:** For each `Position p`, `_position_to_summary(p)` is called. It calls `_summary_sku_and_quantity_from_position(p)` which:
  - Reads `j = p.detected_summary_json`; if missing or not dict → returns `(None, None)`.
  - **sku:** `sku_raw = j.get("internal_code")`; only if non-null, str, and non-empty after strip → `sku = sku_raw.strip()`, else `sku = None`.
  - **detected_quantity:** `q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")`; then `qty = _parse_summary_quantity(q_raw)` (None if raw is None or invalid).
- **Source of `detected_summary_json`:** Persisted by `PersistAisleResultUseCase` from `map_hybrid_report_to_domain(report=...)`. The mapper’s `_detected_summary(entity, audit)` copies from the report entity: `internal_code`, `final_quantity`, `product_label_quantity`, `count_status`, etc. It does **not** copy `position_barcode` or `review_display_label`. So when the report has `internal_code: null`, `final_quantity: null`, `product_label_quantity: null`, the stored summary has those nulls and the list API correctly returns `sku: null`, `detected_quantity: null`.

**Conclusion:** The “failing” path is simply: **report entities have null internal_code / final_quantity / product_label_quantity** (and for quantity, the decision layer sets final_quantity to None for NEEDS_REVIEW/NOT_COUNTABLE). No value is lost in persistence or in the response builder.

## Proposed Fix Plan (ordered)

1. **Confirm intent (no code change):** Decide whether null `sku`/`detected_quantity` for NEEDS_REVIEW/NOT_COUNTABLE and missing internal_code is acceptable. If yes, document it and close as “by design.”
2. **Optional — improve sku display when internal_code is missing (minimal change):**
   - In `src/infrastructure/pipeline/v3_report_mapper.py`, in `_detected_summary()`, add to the output dict:
     - `position_barcode`: `entity.get("position_barcode")`
     - `review_display_label`: from report if present (e.g. `entity.get("review_display_label")`). The report is built with `derive_review_display_label(e.internal_code, e.position_barcode)`, so the report entity may already have `review_display_label`; if so, copy it.
   - In `src/api/routes/inventories_v3.py`, in `_summary_sku_and_quantity_from_position()`, for `sku`: if `internal_code` yields no value, set `sku = (j.get("review_display_label") or j.get("position_barcode"))` and normalize (strip, None if empty). This aligns list display with the same logic as review/export (internal_code else position_barcode).
3. **Optional — show raw quantity when final_quantity is null:** If product wants the table to show `product_label_quantity` when `final_quantity` is null (e.g. for NEEDS_REVIEW), the current logic already uses it: `q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")`. So if both are null in the report, there is nothing to show; no change. If the report has `product_label_quantity` but the API still returns null, then either the summary does not contain it (persistence bug) or the key differs; trace one payload to confirm.

## Regression Prevention (tests + invariants)

- **Unit test for `_summary_sku_and_quantity_from_position`:**  
  - Given `detected_summary_json` with `internal_code: "ABC"`, `final_quantity: 2` → returns `("ABC", 2)`.  
  - Given `internal_code: null`, `review_display_label: "P-001"` (after adding fallback) → returns `("P-001", None)` (or whatever fallback is chosen).  
  - Given `internal_code: null`, `final_quantity: null`, `product_label_quantity: 3` → returns `(None, 3)`.  
  - Given empty or missing summary → returns `(None, None)`.
- **Integration test (optional):** Persist one position with non-null internal_code and final_quantity; GET list; assert `positions[0].sku` and `positions[0].detected_quantity` match.
- **Invariant:** In the list response, for each position, `sku` and `detected_quantity` must be derivable from `position.detected_summary_json` by the documented rules (internal_code for sku; final_quantity else product_label_quantity for quantity; optional fallback for sku). Add a short comment in the schema or in `_position_to_summary` stating that sku/detected_quantity are derived from detected_summary_json and may be null when upstream data is missing.

## Debug Checklist (runbook)

1. **Inspect one position from the list response:**  
   - `position.detected_summary_json.internal_code`  
   - `position.detected_summary_json.final_quantity`  
   - `position.detected_summary_json.product_label_quantity`  
   - `position.detected_summary_json.count_status`  
   If all of the first three are null, the API is correctly returning null.

2. **Inspect the same position in the report file** (e.g. `output_dir/{job_id}/run/hybrid_report.json`):  
   - For the entity that became this position, check `internal_code`, `final_quantity`, `product_label_quantity`, `position_barcode`, `review_display_label`.  
   If they are null in the report, the issue is upstream (parser/decision). If they are present in the report but null in the API, trace mapper and persistence.

3. **Check mapper output:** In `_detected_summary`, confirm which keys are written. Confirm that `position_barcode` / `review_display_label` are not currently stored; if product wants a fallback for sku, add them and the fallback in the list builder.

4. **Check decision layer:** For NEEDS_REVIEW and NOT_COUNTABLE, `assign_count_status` sets `final_quantity = None`. So null `detected_quantity` for those statuses is by design unless `product_label_quantity` is used (already used as fallback when `final_quantity` is None).

5. **Run unit test** for `_summary_sku_and_quantity_from_position` with the above cases to lock behavior and prevent regressions.
