# Analytics DoD And Unknown Backfill Audit

## Overall DoD audit

### Product structure and hierarchy

Status: `complete`

Audit:
- the page structure matches the intended final dashboard hierarchy from `docs/Re factor metrics.md`
- current order is:
  1. filters
  2. KPI cards
  3. operational visuals
  4. inventory performance
  5. quality patterns + aisles requiring attention
- older low-value blocks are no longer part of the delivered metrics module

### KPI set

Status: `partial`

Audit:
- the KPI layer is operational and mostly aligned
- `auto_acceptance_rate`, `manual_correction_rate`, `processing_success_rate`, `average_review_time`, and `invalid_traceability_rate` are present and backed by current contracts
- `unknown_rate` is contractually available and now truthfully supported by the backend model
- however, the current frontend still renders `Unknown rate` conditionally based on backend availability
- this is technically correct, but operationally it means the full six-card experience depends on whether the scoped backend response includes explicit unknown outcomes

Conclusion:
- the KPI system is truthful and acceptable
- the final product experience is not blocked, but operators can still misread the absence of `Unknown rate` as "there are no unknowns" rather than "no explicit unknowns were captured in this scope"

### Operational visuals

Status: `complete`

Audit:
- both required visual sections exist:
  - `Manual intervention breakdown`
  - `Resolution flow`
- they use current supported fields and do not fabricate funnel stages or unsupported categories
- they now read as compact operational components rather than decorative charts

### Inventory performance table

Status: `complete`

Audit:
- the table is promoted and remains the primary comparison surface
- it is paginated, sortable, and uses the additive Phase 2 contract fields with legacy-safe fallbacks
- truthful `unknown_rate` is supported in the contract and can render when available

### Aisles requiring attention

Status: `complete`

Audit:
- the table is secondary, compact, paginated, and action-oriented
- it exposes the intended operational fields now supported by backend:
  - positions
  - pending review
  - unknown
  - invalid traceability
  - manual corrections
- it no longer reads like a generic leftover analytics table

### Quality patterns

Status: `complete`

Audit:
- the block is rendered as a mutually exclusive prioritized issue view
- `Unknown` is now supported by backend and is included when truthfully present
- frontend ordering is deterministic and aligned to the intended product priority model

### Filter and scope behavior

Status: `complete`

Audit:
- inventory and aisle filters drive the page coherently
- aisle options depend on selected inventory
- invalid aisle selection resets correctly
- the scope summary line is explicit
- the all-scope mode remains intentionally supported

### Backend contract quality

Status: `complete`

Audit:
- summary, inventory performance, aisle attention, quality patterns, and manual intervention breakdown all expose typed additive contracts
- earlier compatibility fields remain preserved where the implementation intentionally remained additive
- SQL and memory implementations are meaningfully aligned for the key metrics that drive the page

### Persistence and migration consistency

Status: `complete`

Audit:
- the `positions.review_resolution` schema change is versioned via:
  - `backend/src/database/migrations/versions/0008_add_position_review_resolution.sql`
- `schema.sql` is aligned with the migration
- the design/corrections notes explicitly document historical `NULL` behavior

### Unknown semantics

Status: `complete`

Audit:
- the system now uses an explicit persisted unknown terminal outcome
- analytics do not infer unknown from quantity provenance, missing evidence, or confidence
- this is consistent with the approved business semantics

### Deployment and readiness implications

Status: `partial`

Audit:
- the schema/migration work is deployable and versioned
- the main readiness caveat is historical data interpretation:
  - post-refactor data can be trusted for explicit unknown
  - pre-refactor data can still undercount unknown
- this is documented, but product/operator communication remains important to avoid false historical comparisons

## Current product/UI audit

### Does the page read like an operational dashboard?

Status: `complete`

Audit:
- yes
- the page now emphasizes efficiency, manual effort, quality pressure, inventory comparison, and aisle attention in the intended order

### Are KPI cards correct and truthful?

Status: `partial`

Audit:
- formulas are truthful and mostly aligned to the plan
- the cards do not appear to fabricate values
- the main risk is interpretability:
  - `unknown` is narrower than many operators may assume
  - it means explicit terminal operator unknown only
  - it does not mean all operationally ambiguous or unresolved results

### Is Inventory performance properly prioritized?

Status: `complete`

Audit:
- yes
- it is visually and structurally the primary comparison table

### Is Aisles requiring attention secondary enough?

Status: `complete`

Audit:
- yes
- it is compact, paginated, and clearly subordinate to inventory performance

### Is Quality patterns useful and aligned with the intended priority model?

Status: `complete`

Audit:
- yes
- it is deterministic, readable, and product-prioritized
- `Unknown` is now an explicit bucket when truthfully supported

### Are Manual intervention breakdown and Resolution flow actually helping operators?

Status: `complete`

Audit:
- yes
- they now explain operator outcomes and throughput more clearly
- both visuals are compact and based on real current contract fields

### Are there misleading empty/zero states around unknown?

Status: `partial`

Audit:
- no direct fabrication is happening
- however, a zero or absent unknown signal can still be misread operationally
- the UI truthfully reflects backend support, but older inventories can still look cleaner than they really were because historical explicit unknown capture did not exist

## Unknown semantics audit

### Domain model

Status: `complete`

Audit:
- `backend/src/domain/positions/entities.py` defines:
  - `PositionReviewResolution.UNKNOWN`
- `review_resolution` is explicitly separate from:
  - `status`
  - `needs_review`
  - quantity provenance such as `qty_source="unknown"`

### Persisted fields

Status: `complete`

Audit:
- `positions.review_resolution` is the persisted current-state signal
- `NULL` is an intentional transitional state, not a synonym for unknown

### Review actions

Status: `complete`

Audit:
- `backend/src/domain/reviews/entities.py` defines:
  - `ReviewActionType.MARK_UNKNOWN`
- this gives an auditable terminal operator action

### Summary analytics

Status: `complete`

Audit:
- summary `unknown_rate` and `unknown_count` use explicit reviewed-position semantics
- denominator:
  - reviewed positions with terminal review actions
  - excludes delete-only outcomes
- numerator:
  - latest terminal review outcome `mark_unknown`

### Inventory performance

Status: `complete`

Audit:
- inventory rows expose `unknown_rate`
- it is derived from explicit reviewed-position unknown outcomes

### Aisle-level metrics

Status: `complete`

Audit:
- aisle analytics expose `unknown_count`
- SQL uses `p.review_resolution = 'unknown'`
- memory uses `PositionReviewResolution.UNKNOWN`

### Quality patterns

Status: `complete`

Audit:
- unknown is the highest-priority bucket in both SQL and memory logic
- a position is counted as `Unknown` only when `review_resolution = unknown`

### Frontend rendering

Status: `complete`

Audit:
- frontend types and components support unknown consistently across:
  - summary
  - inventory performance
  - aisle attention
  - quality patterns
  - manual intervention breakdown
  - resolution flow
- frontend does not appear to synthesize unknown locally

### Is meaning consistent everywhere?

Status: `complete`

Audit:
- yes, with one important caveat:
  - "unknown" consistently means explicit terminal operator unknown
  - it does **not** mean "all results that were operationally ambiguous"

### Could the UI be misread as broader unknown detection?

Status: `partial`

Audit:
- yes, by a non-technical operator
- the UI can be read as "the dashboard knows all unknown-like outcomes"
- in reality it only knows:
  - explicit terminal unknown outcomes persisted through the new model

## Historical inventory audit

### Are historical unknowns currently captured?

Status: `partial`

Audit:
- post-refactor inventories reviewed through the new review flow are captured correctly
- pre-refactor inventories are captured only if they later received the new explicit unknown signal

### If an old inventory had many operationally unknown outcomes, will current analytics capture them?

Status: `missing`

Answer:
- not in general
- current analytics will only count them if the historical positions were later touched and persisted with:
  - `positions.review_resolution = unknown`
  - and/or `review_actions.action_type = mark_unknown`

### Exact conditions under which old data is counted as unknown

Status: `complete`

Answer:
- old data is counted as unknown only when a row now carries the explicit persisted terminal unknown signal
- a historical inventory is **not** counted as unknown merely because it contains:
  - `qty_source="unknown"`
  - missing evidence
  - unresolved SKU
  - traceability anomalies
  - old review actions without `mark_unknown`

### Are pre-refactor records missing explicit unknown signals?

Status: `complete`

Answer:
- for pre-refactor inventories, the expected missing signals are:
  - `review_resolution = unknown`
  - `mark_unknown` review actions
- in practice, old records will usually be missing both unless they were revisited after rollout

### Does current analytics intentionally undercount historical unknowns?

Status: `complete`

Audit:
- yes
- that undercount is intentional
- it is the direct result of the approved design choice:
  - no heuristic backfill
  - only explicit terminal unknown counts

### Is that acceptable, risky, or misleading?

Status: `partial`

Audit:
- technically acceptable
- product-risky if operators compare older and newer inventories without context
- not misleading at the computation layer
- potentially misleading at the interpretation layer unless documented as:
  - "historical unknown coverage begins at the explicit unknown-resolution rollout"

## Backfill feasibility audit

### Strategy A: no backfill

Status: `recommended`

Data source:
- none

Confidence:
- highest possible truthfulness

False positive risk:
- none introduced by migration logic

False negative risk:
- high historical undercount remains

Auditability:
- excellent

Reversibility:
- trivial

Operational trust impact:
- strong on correctness
- weaker on historical completeness

Assessment:
- safest default
- requires explicit documentation that historical unknowns are reliable only from the explicit persisted model onward

### Strategy B: backfill only when an explicit legacy signal exists

Status: `conditionally safe`

Possible data source:
- a proven legacy review action or persisted terminal state that is semantically equivalent to today's `mark_unknown`

Confidence:
- high only if such a legacy explicit signal actually exists

False positive risk:
- low if and only if the source is truly explicit and operator-authored

False negative risk:
- medium to high because many historical unknowns may still remain unmarked

Auditability:
- good, if the mapping rule is one-to-one and documented

Reversibility:
- good with a reversible migration or recorded provenance

Operational trust impact:
- acceptable

Assessment:
- currently no evidence in the reviewed model suggests such a trustworthy pre-existing explicit unknown signal exists
- therefore this is theoretically conditionally safe, but not currently justified by the repo state

### Strategy C: backfill from historical review actions that are not semantically equivalent

Status: `not recommended`

Possible data source:
- old `confirm`, `update_quantity`, `update_sku`, or `delete_position` actions

Confidence:
- low

False positive risk:
- high

False negative risk:
- high

Auditability:
- poor

Reversibility:
- technically possible, but business meaning would still be weak

Operational trust impact:
- poor

Assessment:
- historical review actions reviewed in the current repo do not contain a trustworthy old "unknown" equivalent
- mapping them to `unknown` would rewrite business meaning rather than preserve it

### Strategy D: heuristic backfill from snapshot state or quantity provenance

Status: `not recommended`

Possible data source:
- `qty_source="unknown"`
- missing evidence
- absent SKU
- low confidence
- traceability anomalies
- `needs_review`

Confidence:
- low

False positive risk:
- very high

False negative risk:
- also high

Auditability:
- poor

Reversibility:
- technically possible but operationally damaging

Operational trust impact:
- strongly negative

Assessment:
- this directly violates the approved semantics
- these are "unknown-like" technical or operational signals, not explicit terminal operator unknown outcomes

### Strategy E: hybrid strategy

Status: `not recommended`

Possible data source:
- explicit legacy signal where available
- heuristic inference elsewhere

Confidence:
- mixed and hard to explain

False positive risk:
- high in the heuristic subset

False negative risk:
- still substantial

Auditability:
- weak because two different meanings would coexist in the same metric

Reversibility:
- partial

Operational trust impact:
- poor

Assessment:
- this would create a metric whose meaning changes across historical periods
- not recommended

## Schema and migration audit

### Schema versioning

Status: `complete`

Audit:
- the unknown persistence column is versioned with migration `0008_add_position_review_resolution.sql`
- this satisfies the earlier correction requirement that the change must not live only in `schema.sql`

### Readiness and schema-guard expectations

Status: `complete`

Audit:
- migration numbering and idempotent SQL style align with existing project conventions
- the corrections note explicitly confirms readiness integration

### Historical NULL behavior

Status: `complete`

Audit:
- historical `NULL review_resolution` behavior is explicitly understood and documented:
  - `NULL` means no persisted terminal operator resolution on the row
  - `NULL` does not imply unknown
  - no heuristic backfill is performed

### Production safety

Status: `partial`

Audit:
- schema and migration mechanics are production-safe
- the remaining production concern is interpretive rather than technical:
  - old inventories can under-report unknown because the new persistence model did not exist yet

## Contract consistency audit

### Summary

Status: `complete`

Audit:
- backend and frontend both support `unknown_rate` and `unknown_count`
- semantics are consistent with explicit terminal unknown only

### Inventory performance

Status: `complete`

Audit:
- backend and frontend both support `unknown_rate`
- fallback handling for older additive fields is clean

### Aisle attention

Status: `complete`

Audit:
- backend and frontend both support `unknown_count` and `manual_corrections_count`
- the current UI now surfaces them

### Quality patterns

Status: `complete`

Audit:
- backend and frontend both support explicit `Unknown`
- priority ordering is handled on the frontend and unknown bucket logic is handled in backend repositories/core

### Manual intervention breakdown

Status: `partial`

Audit:
- `unknown` is now consistently supported
- `invalid` is intentionally unavailable because the persisted model still does not distinguish invalid from delete
- one denominator nuance remains important:
  - backend percentages use `intervention_positions_count`
  - some earlier planning language favored `reviewed_positions_count`
- this is not a code bug, but it is an operational interpretation caveat

### Resolution flow

Status: `partial`

Audit:
- the UI uses truthful current counts
- however, it blends summary counts and manual-intervention counts into a compact operator flow
- this is useful, but not a strict backend-defined canonical funnel contract

### Does frontend ever show zero where it should show unavailable?

Status: `partial`

Audit:
- explicit unsupported intervention categories are shown as unavailable rather than zero, which is correct
- unknown-specific rendering is generally safe
- the main interpretive risk remains historical undercount, not a frontend availability bug

### Do old inventories distort percentages?

Status: `partial`

Audit:
- yes, potentially
- denominators themselves are technically correct for the current explicit model
- but historical inventories can still show lower unknown percentages than reality because explicit unknown outcomes were not persisted then

## Final recommendation

### Recommended stance

Status: `recommended`

Decision:
- **A. No backfill recommended; document that unknown is reliable only from the refactor onward**

Why:
- the current implementation is truthful, explicit, and auditable
- pre-refactor historical data usually lacks both:
  - `review_resolution = unknown`
  - `mark_unknown`
- no trustworthy reviewed legacy signal was identified in the inspected model that can be cleanly mapped to explicit unknown
- heuristic backfill from quantity provenance, missing evidence, confidence, or traceability would violate the approved semantics and materially reduce operator trust

### Optional stricter variant

Status: `conditionally safe`

Recommendation:
- only consider a limited backfill if a future audit discovers a strict one-to-one explicit legacy unknown signal
- based on the current inspected repo state, that condition is not satisfied

### Practical product recommendation

Status: `recommended`

Recommendation:
- keep historical data as-is
- document clearly that:
  - explicit unknown metrics are trustworthy from the unknown-resolution rollout onward
  - older inventories may undercount unknown
  - historical trend comparisons across the rollout boundary should be interpreted carefully

## Final classification snapshot

- overall metrics module against intended refactor DoD: `partial`
  - reason: the module is functionally strong and mostly complete, but historical unknown coverage remains intentionally incomplete for pre-refactor data, and a few interpretation nuances remain
- unknown semantics implementation: `complete`
- historical unknown capture for pre-refactor inventories: `partial`
- historical backfill via heuristics: `not recommended`
- limited backfill for a strict explicit legacy subset: `conditionally safe`, but not currently justified by available signals
