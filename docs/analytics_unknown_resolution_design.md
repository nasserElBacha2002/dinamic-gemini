# Analytics Unknown Resolution Design

## Goal

Unblock truthful analytics support for `UNKNOWN` by introducing a durable persisted business concept
for the final operator-facing resolution of a position.

This design intentionally avoids heuristics. `UNKNOWN` is only counted when an operator explicitly
resolves a position as unknown through the review flow.

## Final semantics

`unknown` means:
- the final operator-facing review resolution of a position is unknown

`unknown` does not mean:
- quantity provenance is unknown
- `qty_source="unknown"`
- missing SKU inferred from raw data
- missing evidence inferred from raw data
- a position that still has `needs_review = true`
- a position with no operator action yet
- any fallback derived from traceability or confidence

## Persistence model

Phase 4 persists terminal review outcome in two places:

1. `positions.review_resolution`
- new nullable persisted column
- values currently supported:
  - `confirmed`
  - `qty_corrected`
  - `sku_corrected`
  - `unknown`
  - `deleted`
- `NULL` means no terminal operator decision has been persisted yet
- for historical rows created before the Phase 4 migration, `NULL` is the expected transitional state
- this phase does not perform any heuristic or inferred backfill of historical `NULL` rows

2. `review_actions.action_type`
- extended with `mark_unknown`
- preserves the audit trail of the explicit operator action

This gives us both:
- a cheap current-state read model for analytics and quality buckets
- a durable audit trail for traceability

## Review-flow behavior

`mark_unknown` is a terminal manual review action.

When it is applied:
- `positions.review_resolution` becomes `unknown`
- `positions.status` becomes `reviewed`
- `positions.needs_review` becomes `false`
- a `review_actions` audit row is written with `action_type = mark_unknown`

Why `status = reviewed`:
- the operator completed the review flow
- no product correction was applied
- we avoid overloading `status` with an analytics-only state
- `review_resolution` carries the business meaning precisely

## How this differs from other outcomes

### Pending review

Pending review is:
- `needs_review = true`
- or no terminal operator resolution persisted yet

Pending review is not `unknown`.

### Invalid

`invalid` remains a separate blocked topic.

Current persistence still does not distinguish:
- invalid
- delete

Phase 4 does not change that. We keep `invalid` explicitly blocked rather than silently conflating it
with `unknown`.

### Delete

`delete` is represented by:
- `review_actions.action_type = delete_position`
- `positions.review_resolution = deleted`

Deleted is a distinct terminal outcome and must not be counted as unknown.

### `qty_source="unknown"`

This is quantity provenance only.

It may describe how quantity was resolved technically, but it does not represent the final
operator-facing business resolution of the position.

## Analytics now enabled safely

The following analytics can now truthfully use persisted unknown resolution:

- summary:
  - `unknown_rate`
  - `unknown_count`
- inventory performance:
  - `unknown_rate`
- manual intervention breakdown:
  - `unknown` category with real counts
- quality patterns:
  - explicit `Unknown` bucket
- aisle attention:
  - `unknown_count`

Recommended formula:

- `unknown_rate = unknown_positions_count / reviewed_positions_count`

Where:
- `unknown_positions_count` = unique positions whose terminal review resolution is `unknown`
- `reviewed_positions_count` = unique positions with a terminal review action in scope:
  - `confirm`
  - `update_quantity`
  - `update_sku`
  - `mark_unknown`

`delete_position` remains excluded from that denominator.

## Historical transition behavior

During rollout, older positions can still have `review_resolution = NULL`.

Interpretation:
- `NULL` means no persisted terminal operator resolution is available on the row
- it does not imply unknown
- it does not imply pending review by itself; `needs_review` still carries that operational meaning

Phase 4 analytics behavior for historical rows:
- `unknown` is counted only when `review_resolution = unknown`
- `NULL` rows are excluded from unknown counts and unknown rates
- no heuristic backfill is performed from:
  - `qty_source="unknown"`
  - missing evidence
  - traceability
  - absent review actions

This keeps the migration truthful and auditable while legacy rows transition naturally as operators
touch positions through the current review flow.

## Auditability notes

This design is intentionally explicit and auditable:
- the current terminal resolution is persisted on `positions`
- the operator action history remains persisted in `review_actions`
- analytics do not infer unknown from raw CV artifacts or quantity metadata

## Still blocked after Phase 4

- distinct persisted `invalid` terminal review outcome
- any broader invalid-vs-delete analytics split beyond the currently available behavior
