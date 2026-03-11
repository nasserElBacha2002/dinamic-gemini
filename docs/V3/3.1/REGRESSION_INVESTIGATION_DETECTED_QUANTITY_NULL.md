# Regression Investigation: detected_quantity returning null

## 1. Investigation verdict

**Yes, this is a real regression bug** relative to the stated product rule.

**Current null behavior is wrong** given the requirement: *"I must always show how many products were counted."* The positions list API was returning `detected_quantity: null` whenever `final_quantity` and `product_label_quantity` were both null in `detected_summary_json` (common for NEEDS_REVIEW / NOT_COUNTABLE). There was **no fallback to a displayable value**, so the frontend could not show a count.

---

## 2. Exact failing code path

| Layer | File | Function / location |
|-------|------|----------------------|
| Route | `src/api/routes/inventories_v3.py` | `list_aisle_positions()` builds response via `_position_to_summary(p)` for each position |
| DTO builder | Same file | `_position_to_summary(p)` → `sku, detected_quantity = _summary_sku_and_quantity_from_position(p)` → `PositionSummaryResponse(..., detected_quantity=detected_quantity)` |
| Derivation | Same file | `_summary_sku_and_quantity_from_position(p)` |
| Assignment that caused null | Same file, ~lines 260–263 | `q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")` then `qty = _parse_summary_quantity(q_raw)` then **return sku, qty** with no fallback when `qty` is `None` |

When both `final_quantity` and `product_label_quantity` are null in `detected_summary_json`, `q_raw` is `None`, `_parse_summary_quantity(None)` returns `None`, and the function returns `(sku, None)`, so the API responds with `detected_quantity: null`.

---

## 3. What changed (root cause)

- **No recent field rename:** The code has always used `final_quantity` and `product_label_quantity` from `detected_summary_json`; the schema and keys match.
- **No removed fallback in git:** The regression is that **a fallback was never implemented** in the list response path. The list API only ever derived quantity from those two fields and returned `None` when both were null.
- **Upstream behavior:** For NEEDS_REVIEW and NOT_COUNTABLE, the decision layer sets `final_quantity = None`. If the pipeline does not set `product_label_quantity`, both are null in the report and in `detected_summary_json`. So the derivation correctly computed “no resolved quantity” but then returned it as null instead of a displayable value.
- **Mismatch with ProductRecord:** The v3 report mapper assigns `ProductRecord.detected_quantity = max(0, quantity)` and uses 0 when both are null. So the **authoritative** count per position is 0 in the DB for those cases. The list API does not load product records; it only uses `detected_summary_json`, which stores the raw report fields (null). So the list response showed null while the persisted count was 0.

So the regression is **missing fallback in the list derivation**: when the derived quantity is `None`, the API should still expose a numeric value (0) so the frontend can always show a count.

---

## 4. Minimal fix applied

**Change:** In `_summary_sku_and_quantity_from_position` in `src/api/routes/inventories_v3.py`, after `qty = _parse_summary_quantity(q_raw)`, if `qty is None` then set `qty = 0` before returning.

**Effect:**

- When `final_quantity` or `product_label_quantity` is present and valid, behavior is unchanged.
- When both are null (or invalid), the API now returns `detected_quantity: 0` instead of `null`, satisfying “always show how many products were counted” without loading product records or changing the report/mapper contract.

**Code (after fix):**

```python
q_raw = j.get("final_quantity") if j.get("final_quantity") is not None else j.get("product_label_quantity")
qty = _parse_summary_quantity(q_raw)
# Business rule: always show a counted quantity. When unresolved (both null), use 0 so the frontend never gets null.
if qty is None:
    qty = 0
return sku, qty
```

---

## 5. Optional hardening

- **Mapper / DTO tests:** Keep and extend `tests/api/test_position_summary_mapping.py`: assert that when `final_quantity` and `product_label_quantity` are null, `_summary_sku_and_quantity_from_position` returns `qty == 0` (already added/updated).
- **Contract test:** Add a test that the positions list response never has `detected_quantity: null` for any position that has a non-null `detected_summary_json` (e.g. iterate positions and assert `p.detected_quantity is not None` when summary exists).
- **Explicit rule in code:** The comment above the fallback documents the business rule; consider a one-line note in `PositionSummaryResponse` or the route docstring: “detected_quantity is always a number when the position has a summary; 0 when no quantity was resolved.”
- **Snapshot (optional):** If you add response snapshots for GET positions, include an example where summary has null quantity fields and assert the payload has `detected_quantity: 0`.
