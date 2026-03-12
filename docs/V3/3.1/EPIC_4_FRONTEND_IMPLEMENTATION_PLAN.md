# Epic 4 — Frontend implementation (review display label)

**Scope:** Frontend-only. Consume the backend review-oriented display field and surface it in the job entities review UI. No backend changes.

**Source of truth:** Backend `EntityListItem` exposes `review_display_label` (primary) and `product_display_label` (deprecated alias, same value). See `src/api/schemas/responses.py` and Epic 3.1.D plan.

---

## Implemented scope

- **Types:** `JobEntityListItem` in `frontend/src/api/types/responses.ts` includes optional `review_display_label` and `product_display_label`.
- **Job entities page:** New "Review label" column in the count results table; value = `review_display_label ?? product_display_label`, rendered with existing `displayOptional` (— when absent/empty). Column label chosen for review/audit context.
- **Helper:** `getEntityDisplayLabel(entity)` in `JobEntitiesPage.tsx` returns the display value (no duplicate normalization; `displayOptional` handles empty/whitespace).
- **Tests:** Display label column presence, value when present, fallback to `product_display_label`, em dash when both absent/empty, legacy entities still render.

## Out of scope (left for later)

- Position detail page (v3 API) does not use v1 job entities; no change there.
- Dedicated entity detail/evidence view for a single job entity (if added later) can show the same field.
- Tooltip/helper text for "Display label" (optional future improvement).

## Backward compatibility

- When `review_display_label` and `product_display_label` are absent or empty, the column shows "—".
- Legacy responses without these fields render without error; the new column is additive.
