# Analytics Unknown Backfill Discovery

## Scope

This note is a discovery, design, and dry-run simulation pass only.

It does **not**:
- modify production data
- persist any `review_resolution` changes
- add migrations or automatic write paths

It does:
- inspect historical persistence surfaces for trustworthy legacy `unknown` intent
- classify candidate signals by confidence
- simulate likely backfill impact without writes
- recommend whether any safe historical subset exists

Reference documents:
- `docs/Re factor metrics.md`
- `docs/analytics_metrics_phase1_audit.md`
- `docs/analytics_unknown_resolution_design.md`
- `docs/analytics_dod_and_unknown_backfill_audit.md`

## Legacy signal inventory

### 1. Explicit modern unknown signals

Sources inspected:
- `positions.review_resolution`
- `review_actions.action_type`
- `review_actions.before_json`
- `review_actions.after_json`
- `review_actions.comment`

Expected modern-safe markers:
- `positions.review_resolution = 'unknown'`
- `review_actions.action_type = 'mark_unknown'`
- payload/comment text explicitly carrying equivalent operator intent

Dry-run findings on the connected historical dataset:
- positions with `review_resolution = 'unknown'`: `0`
- review actions with `action_type = 'mark_unknown'`: `0`
- review action comments containing `unknown`: `0`
- review action `before_json` / `after_json` containing `unknown`: `0`

Classification:
- `explicit safe signal` in principle
- `not present` in the inspected historical data

Conclusion:
- there is no currently observed legacy explicit signal that can be automatically mapped to historical `unknown`

### 2. Historical review actions without explicit unknown

Sources inspected:
- `review_actions.action_type`
- representative `before_json` / `after_json` payloads

Observed legacy action set in the connected dataset:
- `confirm`: `23`
- `update_quantity`: `2`
- `update_sku`: `3`
- `delete_position`: `0`
- `mark_unknown`: `0`

Observed payload shape in sampled rows:
- `confirm` transitions only reflect status changes such as `detected -> reviewed`
- `update_quantity` records corrected quantity deltas
- `update_sku` records SKU/description changes
- no sampled payload carried explicit unknown-like terminal meaning

Classification:
- `unusable signal` for automatic unknown backfill

Why:
- these actions encode confirm/correction semantics, not operator-facing unknown semantics

### 3. Quantity provenance and quantity resolution artifacts

Sources inspected:
- `product_records.qty_source`
- `product_records.qty_parse_status`
- `positions.detected_summary_json`
- `positions.corrected_summary_json`
- quantity mapping logic in:
  - `backend/src/infrastructure/pipeline/v3_report_mapper.py`
  - `backend/src/application/mappers/position_canonical_view.py`
  - `backend/src/domain/quantity/resolution.py`

Important code semantics:
- `qty_source = 'unresolved'` means quantity could not be resolved/materialized
- it is a technical quantity-resolution outcome
- it is **not** a final operator review outcome
- `qty_source = 'unknown'` is legacy quantity provenance wording, not review resolution wording

Dry-run findings on the connected historical dataset:
- `product_records.qty_source = 'unresolved'`: `30` product rows / `30` distinct positions
- `qty_source = 'unknown'`: `0`
- `detected_summary_json` containing literal `unknown`: `0`
- `corrected_summary_json` containing literal `unknown`: `0`

Classification:
- `heuristic risky signal`

Why:
- it describes quantity non-resolution, not explicit terminal operator unknown
- all `qty_source = 'unresolved'` rows in the inspected data are still pending:
  - positions with unresolved qty and review actions: `0`
  - positions with unresolved qty and no review actions: `30`
  - positions with unresolved qty and `needs_review = true`: `30`
  - positions with unresolved qty and settled review state: `0`

Conclusion:
- unresolved quantity is evidence of incomplete technical resolution, not of operator-declared unknown

### 4. Pending review and unresolved operational state

Sources inspected:
- `positions.needs_review`
- `positions.status`
- review action presence/absence

Dry-run findings on the connected historical dataset:
- total positions: `250`
- `needs_review = true`: `140`
- `status = reviewed`: `22`
- `status = corrected`: `2`

Classification:
- `unusable signal`

Why:
- pending review explicitly means the opposite of terminal operator resolution
- absent review actions means no persisted decision, not an unknown decision

### 5. Structural / quality / ambiguity indicators

Sources inspected:
- `detected_summary_json._audit.internal_code_missing`
- `detected_summary_json._audit.explicit_quantity_missing`
- `detected_summary_json.count_status`
- `detected_summary_json.traceability_status`
- product SKU values such as `UNKNOWN`

Dry-run findings on the connected historical dataset:
- positions with `internal_code_missing = true`: `71`
- positions with `explicit_quantity_missing = true`: `154`
- positions with `count_status = 'NOT_COUNTABLE'`: `31`
- positions with `count_status = 'INVALID_STRUCTURE'`: `2`
- positions with product SKU `UNKNOWN`: `71`
- positions with `traceability_status = 'invalid'`: `0`
- positions missing `primary_evidence_id`: `0`

Classification:
- `heuristic risky signal` for:
  - `SKU = UNKNOWN`
  - internal code missing
  - explicit quantity missing
  - `NOT_COUNTABLE`
  - `INVALID_STRUCTURE`
- `unusable signal` for invalid traceability in the inspected dataset because there are no matching rows

Why:
- these conditions describe CV ambiguity, missing fields, or technical structure problems
- none of them prove an operator explicitly resolved the position as unknown
- several of them overlap with pending review rather than terminal settlement

## Candidate rules

### A. Safe automatic backfill

#### Rule A1: legacy explicit unknown marker

Status:
- `safe in theory`
- `no eligible rows found in the inspected dataset`

Data source(s):
- `review_actions.action_type`
- `review_actions.before_json`
- `review_actions.after_json`
- `review_actions.comment`
- `positions.review_resolution`

Logical condition:
- only backfill rows where a pre-refactor persisted artifact shows a one-to-one explicit operator-facing unknown meaning equivalent to modern `mark_unknown`

Expected semantic meaning:
- explicit terminal operator unknown resolution

False positive risk:
- very low, if and only if the marker is explicit and operator-authored

False negative risk:
- high, because many historical unknowns may still have no explicit marker

Auditability:
- high

Reversibility:
- high, if writes record provenance and only touch rows without modern explicit unknown

Dry-run result:
- no candidate rows found in the connected dataset

Practical conclusion:
- there is currently **no safe automatic backfill subset**

### B. Review-required candidates

These may be useful for reporting, manual triage, or future operator review workflows, but they are not safe for automatic persistence into `review_resolution = unknown`.

#### Rule B1: unresolved quantity plus still pending review

Data source(s):
- `product_records.qty_source = 'unresolved'`
- `positions.needs_review = true`
- no review actions present

Logical condition:
- classify rows with unresolved quantity and no review action as historical unknown candidates for review only

Expected semantic meaning:
- "operator may need to review this because quantity was unresolved"

Why this is not safe automatically:
- it reflects unresolved technical quantity state, not terminal operator intent
- in the inspected data, all `qty_source = 'unresolved'` rows are still pending and untouched

False positive risk:
- high for automatic unknown

False negative risk:
- medium

Auditability:
- medium if used as a review queue/report only

Reversibility:
- good if never auto-written

Dry-run result:
- `30` positions across `3` inventories
- inventory breakdown:
  - `b-floresta`: `22`
  - `prueba-01`: `6`
  - `prueba-worker-ondemand-1`: `2`

#### Rule B2: not-countable / invalid-structure rows as manual review list

Data source(s):
- `positions.detected_summary_json.count_status`

Logical condition:
- report rows with:
  - `count_status = 'NOT_COUNTABLE'`
  - `count_status = 'INVALID_STRUCTURE'`

Expected semantic meaning:
- structural ambiguity worthy of manual inspection

Why this is not safe automatically:
- these are CV/result-shape states, not operator terminal outcomes
- they may map to delete, correction, continued review, or unknown depending on later human action

False positive risk:
- high for automatic unknown

False negative risk:
- medium

Auditability:
- medium as reporting only

Reversibility:
- good if never auto-written

Dry-run result:
- `NOT_COUNTABLE`: `31`
- `INVALID_STRUCTURE`: `2`
- concentrated in:
  - `b-floresta`
  - `prueba-01`
  - `prueba-worker-ondemand-1`

### C. Rejected rules

#### Rule C1: `needs_review = true` implies unknown

Decision:
- rejected

Why:
- pending review is explicitly non-terminal
- this would rewrite "awaiting review" into "final unknown"

Dry-run impact:
- `140` positions across `5` inventories
- broadest affected inventories:
  - `b-floresta`: `119`
  - `prueba-01`: `7`
  - `prueba-worker-2`: `6`
  - `prueba-reference-image-1`: `4`
  - `prueba-worker-ondemand-1`: `4`

Risk:
- extreme semantic corruption

#### Rule C2: `qty_source = 'unresolved'` implies unknown

Decision:
- rejected

Why:
- quantity non-resolution is not review resolution
- all matching rows in the inspected data are still pending and untouched

Dry-run impact:
- `30` positions across `3` inventories

Risk:
- high false positives

#### Rule C3: product SKU `UNKNOWN` implies unknown

Decision:
- rejected

Why:
- this encodes missing/placeholder identity, not operator terminal resolution
- it overlaps strongly with missing code and pending-review ambiguity

Dry-run impact:
- `71` positions across `3` inventories
- biggest inventories:
  - `b-floresta`: `52`
  - `prueba-worker-ondemand-1`: `13`
  - `prueba-01`: `6`

Risk:
- very high false positives

#### Rule C4: internal code missing implies unknown

Decision:
- rejected

Why:
- missing SKU/código is a product-identity problem, not a proved final operator decision

Dry-run impact:
- `71` positions across `3` inventories

Risk:
- very high false positives

#### Rule C5: explicit quantity missing implies unknown

Decision:
- rejected

Why:
- missing explicit quantity is a technical evidence gap, not terminal review intent

Dry-run impact:
- `154` positions across `7` inventories
- biggest inventories:
  - `b-floresta`: `119`
  - `prueba-worker-2`: `14`
  - `prueba-01`: `9`

Risk:
- extreme over-classification

#### Rule C6: not-countable or invalid-structure implies unknown

Decision:
- rejected

Why:
- these states can lead to many valid downstream operator outcomes
- there is no one-to-one equivalence to unknown

Dry-run impact:
- `33` positions total

Risk:
- high false positives and poor audit semantics

#### Rule C7: absence of review actions implies unknown

Decision:
- rejected

Why:
- no audit trail means no persisted operator decision
- this would convert silence into a terminal business outcome

Risk:
- unacceptable

## Rejected rules

Summary rejection matrix:

| Rule | Status | Main reason |
|---|---|---|
| `needs_review = true` | Rejected | pending, not terminal |
| no review actions | Rejected | absent decision is not unknown |
| `qty_source = unresolved` | Rejected | technical quantity state only |
| product SKU `UNKNOWN` | Rejected | placeholder identity, not resolution |
| `internal_code_missing = true` | Rejected | evidence/identity gap only |
| `explicit_quantity_missing = true` | Rejected | evidence gap only |
| `count_status = NOT_COUNTABLE` | Rejected | ambiguous technical state |
| `count_status = INVALID_STRUCTURE` | Rejected | ambiguous technical state |
| traceability anomalies | Rejected | not equivalent to unknown; also no observed hits here |

## Simulation findings

### Dataset-level findings

Connected dataset snapshot:
- `positions`: `250`
- `review_actions`: `28`

Modern explicit unknown coverage:
- explicit `review_resolution = unknown`: `0`
- explicit `mark_unknown` actions: `0`

Historical signal quality:
- explicit legacy unknown marker: `0`
- unresolved quantity positions: `30`
- pending-review positions: `140`
- SKU `UNKNOWN` positions: `71`
- internal-code-missing positions: `71`
- explicit-quantity-missing positions: `154`

### Inventory-level impact

Potential material changes if rejected heuristics were used:

`qty_source = unresolved`:
- `b-floresta`: `22`
- `prueba-01`: `6`
- `prueba-worker-ondemand-1`: `2`

`needs_review = true`:
- `b-floresta`: `119`
- `prueba-01`: `7`
- `prueba-worker-2`: `6`
- `prueba-reference-image-1`: `4`
- `prueba-worker-ondemand-1`: `4`

`SKU = UNKNOWN` or `internal_code_missing = true`:
- `b-floresta`: `52`
- `prueba-worker-ondemand-1`: `13`
- `prueba-01`: `6`

`explicit_quantity_missing = true`:
- `b-floresta`: `119`
- `prueba-worker-2`: `14`
- `prueba-01`: `9`
- `prueba-reference-image-1`: `4`
- `prueba-worker-ondemand-1`: `4`
- `prueba-02`: `2`
- `pruebalocal`: `2`

### Suspicious breadth observations

The strongest warning signs from the dry run are:
- the only candidate with somewhat intuitive "unknown-like" wording, `qty_source = unresolved`, affects `30` rows but **all 30 are still pending and have no review action**
- the broader missing-evidence and pending-review heuristics would massively inflate unknown:
  - `140` rows from `needs_review`
  - `154` rows from `explicit_quantity_missing`
- none of these rows carry explicit terminal operator evidence

Conclusion:
- the dry run supports the prior audit stance that heuristic backfill would distort metric meaning

## Risk assessment

### Semantic risk

Status:
- `high`

Reason:
- historical artifacts mostly describe CV ambiguity, unresolved quantity, or pending review
- they do not encode the approved business meaning:
  - final operator-facing terminal unknown resolution

### False positive risk

Status:
- `high` to `extreme` for all heuristic candidates

Most dangerous rules:
- `needs_review = true`
- explicit quantity missing
- missing SKU/internal code

### False negative risk

Status:
- `high` even if a strict subset were used

Reason:
- historical data simply appears not to contain a durable explicit unknown concept

### Auditability risk

Status:
- `high` for heuristics

Reason:
- a future reviewer could not defend why a given row became unknown instead of pending, corrected, deleted, or invalid

### Trust / product interpretation risk

Status:
- `high`

Reason:
- historical unknown percentages would look more complete, but they would no longer mean the same thing as post-refactor explicit unknown

## Recommended strategy

### Recommendation

Decision:
- `D. Historical unknown should remain forward-only and be documented`

Operational wording:
- no historical automatic backfill is currently safe
- the safe automatic subset size is effectively `0` in the inspected dataset

Why:
- no trustworthy legacy explicit unknown signal was found
- all observed broad signals are technical ambiguity indicators, not operator terminal outcomes
- dry-run impact shows that heuristic rules would materially and misleadingly rewrite history

### Narrow conditional exception

Status:
- `strict subset only, if future evidence is found`

If a future audit discovers a true one-to-one legacy explicit unknown marker, a write phase could target **only** that subset.

That subset would have to satisfy all of:
- persisted before the refactor
- explicitly operator-authored or system-authored as a direct review outcome
- semantically equivalent to modern `mark_unknown`
- auditable row-by-row
- reversible with provenance

Current dataset result:
- no such rows found

### What should remain excluded

Exclude from any future automatic backfill:
- rows with `needs_review = true`
- rows with no review action
- rows with `qty_source = unresolved`
- rows with product SKU `UNKNOWN`
- rows with missing code / missing quantity / not-countable / invalid-structure flags
- rows inferred from confidence, missing evidence, or traceability heuristics

## If approved later: implementation approach

This section defines the safe shape of a future implementation only. It does **not** authorize execution.

### Delivery mechanism

Preferred approach:
- one-off admin script or explicit admin task

Do **not** use:
- automatic startup migration
- schema migration that writes business backfill values implicitly

Reason:
- this is data interpretation work, not schema evolution
- it should run only after explicit approval, a dry-run review, and row-level signoff

### Required dry-run/report phase

Before any write phase:
- produce a dry-run report of every would-be updated row
- include:
  - position id
  - inventory id / name
  - aisle id
  - legacy signal used
  - rule id
  - current review action history
  - current `review_resolution`
  - proposed new resolution

### Write safeguards

Any future write tool should:
- skip rows that already have explicit modern unknown:
  - `positions.review_resolution = 'unknown'`
  - or existing `mark_unknown` action
- only touch rows that match the approved strict explicit rule set
- run in batches
- emit a machine-readable audit log

### Provenance tracking

If approved later, do not backfill silently.

Record provenance explicitly, for example by:
- adding a review action that clearly marks system backfill provenance
- or adding dedicated backfill metadata such as:
  - `backfilled_unknown_rule`
  - `backfilled_unknown_at`
  - `backfilled_unknown_run_id`

Preferred provenance rule:
- every backfilled row must be traceable to one deterministic rule id

### Rollback approach

Rollback must be straightforward:
- only revert rows written by the approved backfill run id
- never revert rows that were already explicit modern unknown before the run

### Future prompt guidance

If a future implementation prompt is approved, it should target:
- `strict subset only`

But based on the current discovery results, that strict subset is:
- `empty unless a new explicit legacy marker is discovered first`

## Final conclusion

The discovery pass reinforces the existing semantic boundary:
- `unknown` is safe only when it means an explicit terminal operator-facing outcome

For the inspected historical dataset:
- no safe automatic backfill rows were found
- all plausible broad signals are heuristics or pending states
- the correct next stance is to keep historical unknown forward-only unless a future dataset audit uncovers a real explicit legacy marker
