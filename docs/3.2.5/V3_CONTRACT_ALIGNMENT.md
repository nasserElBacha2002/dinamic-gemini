# v3 Contract Alignment (Release 3.2.5 Phase 2)

This document records contract inconsistencies identified in Phase 2 and the implementation notes for their resolution.

---

## corrected_quantity missing in list vs present in detail

**Issue**: `GET .../positions` did not populate `corrected_quantity` on each position summary, while `GET .../positions/{position_id}` did populate it from the display primary product. The frontend uses `resolvedQty = corrected_quantity ?? qty`, so the list view could show the uncorrected pipeline quantity while the detail view showed the manually corrected quantity.

**Implementation note (Phase 2 Block 1)**:
- The list contract was aligned with detail. In `backend/src/api/routes/v3/positions.py`, the list endpoint now computes `corrected_quantity` from the same display primary product (first by `created_at`, `id`) and passes it into `position_to_summary(...)`.
- Both list and detail now expose the display primary product’s manual override consistently; no schema or response shape change was required.
