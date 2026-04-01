# Analytics Unknown Semantic Split

## Goal

The analytics module previously used the single word `unknown` for two different business concepts:

1. an explicit terminal review outcome from the operator flow
2. a product-identification failure where the product row still carries `sku = 'UNKNOWN'`

This note defines the split so the dashboard and contracts stop conflating them.

## Final names

### 1. Operator-marked unknown

Code-facing naming:
- `operator_marked_unknown_rate`
- `operator_marked_unknown_count`
- manual intervention category: `operator_marked_unknown`

Meaning:
- explicit terminal operator-facing unknown outcome from the review flow

Persisted source of truth:
- `positions.review_resolution = 'unknown'`
- `review_actions.action_type = 'mark_unknown'`

Important:
- this is the existing Phase 4 review/domain concept
- it remains preserved
- compatibility aliases such as `unknown_rate` and `unknown_count` still map to this concept only

### 2. Unidentified product

Code-facing naming:
- `unidentified_product_rate`
- `unidentified_product_count`

Meaning:
- the product for the position could not be identified correctly

Backend source of truth:
- display-primary product row for the position has `sku = 'UNKNOWN'`

Current implementation rule:
- use the same display-primary selection rule already used elsewhere in v3 summaries:
  - earliest `ProductRecord.created_at`, then `id`
- classify as unidentified product only when that display-primary row exists and
  `UPPER(TRIM(sku)) = 'UNKNOWN'`

Important:
- this is not a review action
- this is not inferred from pending review, unresolved quantity, low confidence, or missing evidence

## What changed

### Summary analytics

Summary now exposes both concepts:
- operator-marked unknown:
  - `operator_marked_unknown_rate`
  - `operator_marked_unknown_count`
- unidentified product:
  - `unidentified_product_rate`
  - `unidentified_product_count`

Compatibility:
- legacy `unknown_rate`
- legacy `unknown_count`

These compatibility aliases still mean:
- operator-marked unknown only

### Inventory performance

Inventory rows now expose:
- `operator_marked_unknown_rate`
- `unidentified_product_rate`

Dashboard usage:
- the table uses `Unidentified product rate`
- this keeps the main comparison table focused on product-identification quality rather than review action outcomes

### Aisles requiring attention

Aisle rows now expose:
- `operator_marked_unknown_count`
- `unidentified_product_count`

Dashboard usage:
- the table shows `Unidentified product`
- this keeps the secondary operational table aligned to current identification pressure

Compatibility:
- legacy `unknown_count` remains mapped to operator-marked unknown

### Manual intervention breakdown

This block remains review/action-oriented.

It uses:
- `confirmed`
- `qty_corrected`
- `sku_corrected`
- `operator_marked_unknown`
- `deleted`

It does not use:
- `unidentified_product`

Reason:
- unidentified product is not itself a persisted review action category

### Resolution flow

Resolution flow uses:
- `Operator-marked unknown`

It does not use:
- `Unidentified product`

Reason:
- the flow is meant to describe review progression and operator outcomes

### Quality patterns

Quality patterns now use:
- `Unidentified product`

They do not use:
- operator-marked unknown

Reason:
- product-identification failure is the quality-pattern concept the product actually wants to track
- operator-marked unknown is a review outcome and belongs in action-oriented surfaces instead

## Formula decisions

### Operator-marked unknown

Formula:
- `operator_marked_unknown_rate = operator_marked_unknown_count / reviewed_positions_count`

Where:
- `operator_marked_unknown_count` = unique positions whose latest terminal review action in scope is `mark_unknown`

### Unidentified product

Formula:
- `unidentified_product_rate = unidentified_product_count / total_positions_in_scope`

Where:
- `unidentified_product_count` = in-scope non-deleted positions whose display-primary product row has `sku = 'UNKNOWN'`

## Dashboard placement

### Operator-marked unknown appears in

- summary contract
- manual intervention breakdown
- resolution flow
- additive inventory and aisle contracts for explicit semantics

### Unidentified product appears in

- summary KPI surface
- inventory performance
- aisles requiring attention
- quality patterns

## Non-goals

This split does not:
- rename persisted DB enum values
- remove the existing explicit unknown review outcome
- backfill historical operator-marked unknown values
- infer unidentified product from heuristics beyond the chosen SKU rule

## Rationale

This split keeps both concepts truthful:
- operator-marked unknown remains an auditable review outcome
- unidentified product becomes the explicit product-quality metric the dashboard can surface without pretending it came from the review flow
