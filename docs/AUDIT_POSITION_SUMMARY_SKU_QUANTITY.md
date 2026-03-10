# Backend Audit — Position Summary sku/detected_quantity

## 1. Executive verdict

**READY**

The change is correct, robust, and maintainable for frontend consumption. The response schema exposes `sku` and `detected_quantity` as optional first-class fields; the derivation from `detected_summary_json` uses the same keys as the pipeline mapper and handles missing/malformed data with explicit `None`. Quantity parsing supports int, float, and numeric strings and rejects negatives and invalid values. The implementation is documented as a summary-extraction path with ProductRecord as the long-term source of truth. Test coverage includes valid extraction, fallback precedence, numeric strings, and invalid/negative quantity. No blocking issues; one low-severity edge case (non-string `internal_code`) is acceptable to defer.

---

## 2. What is correct

- **API contract:** `PositionSummaryResponse` defines `sku: Optional[str] = None` and `detected_quantity: Optional[int] = None` explicitly. Optionality matches “when derivable”; the list endpoint returns a stable list of summaries with these fields present or null. Schema docstring describes the behavior; endpoint docstring is functional (“List result positions for an aisle. Response includes summary sku and detected_quantity when available.”).

- **Mapping correctness:** Extraction uses `internal_code`, `final_quantity`, and `product_label_quantity`, matching `v3_report_mapper._detected_summary` and the mapper’s persistence. No fabricated values: when JSON is missing or invalid, the helper returns `(None, None)`. Quantity precedence is documented (final_quantity then product_label_quantity) and matches the mapper’s resolution order.

- **Quantity parsing:** `_parse_summary_quantity` handles `None`, int, float, and non-empty numeric strings; rejects negative and invalid values; returns `None` for empty string or non-numeric string. Deterministic and easy to follow.

- **Source-of-truth documentation:** The helper docstring states that this is a “summary-extraction path for list responses only,” that “the authoritative source of truth for product data is ProductRecord,” and that we derive from `detected_summary_json` to avoid loading product records in the list flow. Precedence is explained in code and docstring.

- **Route layer:** The list handler remains thin: it calls the use case and maps each `Position` to `PositionSummaryResponse` via `_position_to_summary`. No business logic in the route; derivation is confined to the mapping helper.

- **Tests:** Six tests cover: populated summary (sku + quantity); fallback to `product_label_quantity` when `final_quantity` is absent; missing/None `detected_summary_json`; full `_position_to_summary` response shape; numeric string quantity; negative and invalid quantity. No silent fabrication is tested implicitly by the invalid/negative and empty-JSON cases.

---

## 3. Issues found

### Critical
- None.

### High
- None.

### Medium
- None.

### Low

- **Non-string `internal_code` in JSON:** The pipeline mapper stores `entity.get("internal_code")` in `detected_summary_json` without coercing type; the report could theoretically contain a number. The API helper only accepts `isinstance(sku_raw, str)` and otherwise leaves `sku` as `None`. So a numeric code would appear as missing in the list, while the persisted `ProductRecord.sku` (from the same mapper) is always a string. **Why it matters:** If a future pipeline or import ever wrote a numeric `internal_code` into the summary JSON, the list would show no SKU. **Recommendation:** Defer unless product owners expect numeric codes. If needed later, coerce to string for display, e.g. `str(sku_raw).strip() if sku_raw is not None else ""`, and treat empty as None.

---

## 4. Contract assessment

The API response shape is suitable for frontend use. The list endpoint returns `positions: List[PositionSummaryResponse]` with each item having optional `sku` and `detected_quantity`. The frontend can rely on these fields when present and use a fallback (e.g. “—”) when null. The contract is explicit, stable, and does not require the client to parse `detected_summary_json`. Optionality is correct: both fields may be null when the position has no summary or when the summary lacks valid data.

---

## 5. Mapping/source-of-truth assessment

Deriving `sku` and `detected_quantity` from `detected_summary_json` is acceptable for the current stage. The mapper writes that JSON at persist time from the same report entity that creates the primary ProductRecord, so for pipeline-generated data the summary and the product record are aligned. The risk is drift if: (1) product data is later updated (e.g. by a review flow) only in ProductRecord and not in `detected_summary_json`, or (2) manual or bulk imports write ProductRecord without updating the position’s summary JSON. The code does not claim otherwise: it documents that this is a summary-extraction path and that ProductRecord is the authoritative source. For a list view that does not load product records, this is a reasonable trade-off; the detail endpoint continues to expose full product records. No change required for this audit; if the product roadmap adds in-place corrections, consider enriching the list from ProductRecord later (e.g. primary product per position) without breaking the current contract.

---

## 6. Test assessment

Current tests are sufficient for the summary mapping and for safe frontend use. Covered: valid extraction with both quantity fields; fallback from `final_quantity` to `product_label_quantity`; missing `detected_summary_json`; full `_position_to_summary` output; numeric string quantity; negative quantity; invalid string quantity. Not covered but low impact: empty dict `detected_summary_json` (behavior is correct: both None); non-string `internal_code` (returns None, no crash). Optional additions if desired later: one test with `detected_summary_json={}` to lock empty-dict behavior; one test with `internal_code: 12345` to document that we do not coerce and return None (or add coercion and test the new behavior).

---

## 7. Blocking fixes before using this in frontend

None. The implementation is ready for frontend consumption.

---

## 8. Deferrable improvements

- Add a test that `detected_summary_json={}` yields `(None, None)` to lock empty-dict behavior.
- If the product roadmap introduces numeric or non-string codes in the report, consider coercing `internal_code` to string for display in the list summary and document the behavior.
- When adding review/correction flows that update ProductRecord, consider whether the list summary should be refreshed from the primary product (e.g. via a small enrichment in the use case or a separate “list summary” projection) and document the choice.

---

## 9. Final recommendation

**Keep and use the implementation.** No blocking fixes are required. The contract is clear, the mapping is correct and robust, and the tests give adequate confidence. Proceed with frontend integration; address the low-severity edge case and deferrable improvements in a later iteration if they become relevant.
