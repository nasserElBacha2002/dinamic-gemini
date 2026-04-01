# Analytics Phase 4 Corrections

## Scope

This note records the focused hardening pass applied after code review of the Phase 4 unknown
resolution work.

## What was corrected

- Added the missing versioned database migration for `positions.review_resolution`
- Kept `schema.sql` aligned, but removed reliance on `schema.sql` alone for rollout safety
- Reviewed SQL and memory analytics parity for:
  - `reviewed_positions_count`
  - `auto_acceptance_rate`
  - `manual_correction_rate`
  - `unknown_rate`
  - delete exclusion from the reviewed denominator
- Corrected SQL analytics so `mark_unknown` is treated consistently with the shared application-layer
  reviewed-outcome semantics for:
  - settling action counts
  - average review time first-settling-action logic
- Tightened docs and route copy to keep:
  - `unknown` = explicit persisted terminal operator outcome
  - `invalid` = still blocked until modeled separately from `delete_position`

## Migration file added

- `backend/src/database/migrations/versions/0008_add_position_review_resolution.sql`

The migration is idempotent and compatible with the existing migration service, which auto-discovers
the highest numbered SQL migration in `backend/src/database/migrations/versions/`.

## Historical null handling

Older rows may still have `positions.review_resolution = NULL`.

Interpretation:
- `NULL` means no persisted terminal operator resolution is available on that row
- it does not mean `unknown`
- it is not heuristically backfilled in this phase

Analytics behavior:
- `unknown` is counted only when `review_resolution = unknown`
- `NULL` rows are excluded from unknown counts/rates
- no backfill is derived from quantity provenance, missing evidence, or traceability

## Semantic alignment outcome

SQL and memory analytics are aligned on these points:

- reviewed denominator includes terminal review actions:
  - `confirm`
  - `update_quantity`
  - `update_sku`
  - `mark_unknown`
- `delete_position` is excluded from the reviewed denominator
- `manual_correction_rate` remains narrow:
  - quantity corrections
  - SKU corrections
- `unknown_rate` uses only the explicit persisted unknown outcome

## Remaining blocked item

- `invalid` remains blocked as a distinct terminal review outcome because current persistence still
  does not distinguish invalid from `delete_position`
