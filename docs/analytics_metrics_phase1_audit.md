# Analytics Metrics Phase 1 Audit

## Objetivo
Align Phase 1 from `docs/Re factor metrics.md` to the current backend analytics implementation without redesigning the dashboard yet.

This note documents:
- the current analytics endpoints and payloads;
- the current calculation source for each block;
- the ambiguities and data-model gaps found;
- the proposed KPI formulas for the next phase;
- the target backend contracts for Phase 2.

## Alcance
In scope for this document:
- current v3 analytics API endpoints;
- analytics response schemas and DTOs;
- analytics query service and repositories;
- canonical position/review concepts needed to define `unknown`, manual intervention, and review efficiency metrics.

Out of scope for this phase:
- frontend dashboard redesign;
- endpoint removal or large payload changes;
- implementing new analytics widgets;
- broad refactors of repositories or persistence.

## Current analytics module map

### Endpoints

| Endpoint | Current response schema | Route/service path | Current calculation source |
|---|---|---|---|
| `/api/v3/analytics/summary` | `AnalyticsSummaryResponse` | `backend/src/api/routes/v3/analytics_api.py` -> `AnalyticsQueryService.summary()` | `AnalyticsRepository.get_summary()` in SQL / memory repos |
| `/api/v3/analytics/trends` | `AnalyticsTrendsResponse` | `backend/src/api/routes/v3/analytics_api.py` -> `AnalyticsQueryService.trends()` | `AnalyticsRepository.get_trends()` |
| `/api/v3/analytics/inventories` | `InventoryPerformanceListResponse` | `backend/src/api/routes/v3/analytics_api.py` -> `AnalyticsQueryService.inventory_performance()` | `AnalyticsRepository.get_inventory_performance()` |
| `/api/v3/analytics/aisles` | `AisleIssueListResponse` | `backend/src/api/routes/v3/analytics_api.py` -> `AnalyticsQueryService.aisle_issues()` | `AnalyticsRepository.get_aisle_issues()` |
| `/api/v3/analytics/quality` | `QualityPatternListResponse` | `backend/src/api/routes/v3/analytics_api.py` -> `AnalyticsQueryService.quality_patterns()` | `AnalyticsRepository.get_quality_patterns()` |

### Main backend files involved

- `backend/src/api/routes/v3/analytics_api.py`
- `backend/src/api/schemas/analytics_schemas.py`
- `backend/src/application/dto/analytics_dto.py`
- `backend/src/application/services/analytics_query_service.py`
- `backend/src/application/services/analytics_aggregation_core.py`
- `backend/src/application/ports/analytics_repository.py`
- `backend/src/infrastructure/repositories/sql_analytics_repository.py`
- `backend/src/infrastructure/repositories/memory_analytics_repository.py`
- `backend/src/application/mappers/position_canonical_view.py`
- `backend/src/domain/reviews/entities.py`
- `backend/src/domain/products/entities.py`

## Current contracts and fields

### `/api/v3/analytics/summary`

Current fields:
- `auto_acceptance_rate`
- `manual_correction_rate`
- `invalid_traceability_rate`
- `processing_success_rate`
- `average_review_time_seconds`
- `settling_actions_per_day`
- `notes`
- `period_day_count`
- `settling_actions_count`
- `positions_in_scope`

Current behavior:
- `auto_acceptance_rate` and `manual_correction_rate` are based on review actions in period.
- `invalid_traceability_rate` is based on current position state, not review actions in period.
- `processing_success_rate` is based on aisle job outcomes in period.
- `average_review_time_seconds` is based on first settling action minus `position.created_at`.
- `settling_actions_per_day` is action-count based, not position-count based.

### `/api/v3/analytics/trends`

Current fields:
- `reviewed_results_over_time[]`
- `correction_rate_over_time[]`
- `processing_success_over_time[]`

Each trend point currently returns:
- `period`
- `reviewed_results`
- `correction_rate`
- `processing_success_rate`

Current behavior:
- `reviewed_results` is actually settling-action count, not unique resolved positions.
- trends only return data when both `date_from` and `date_to` are present.
- this block is explicitly low-value per the Phase 1 plan and should not be expanded further.

### `/api/v3/analytics/inventories`

Current fields per row:
- `inventory_id`
- `inventory_name`
- `inventory_created_at`
- `total_aisles`
- `total_positions`
- `processed_positions`
- `review_rate`
- `correction_rate`
- `invalid_traceability_rate`
- `avg_confidence`
- `processing_success_rate`

Current behavior:
- `review_rate` is unique reviewed positions / total positions.
- `correction_rate` is correction actions / settling actions.
- `processed_positions` is inferred from current `Position` state:
  - `reviewed`
  - `corrected`
  - or `detected` with `needs_review = false`
- there is no `unknown_rate`.
- there is no `average_review_time_minutes`.

### `/api/v3/analytics/aisles`

Current fields per row:
- `aisle_id`
- `aisle_code`
- `inventory_id`
- `inventory_name`
- `total_results`
- `needs_review_count`
- `corrected_count`
- `invalid_traceability_count`
- `low_confidence_count`
- `most_common_issue`

Current behavior:
- this is a quality / review-pressure table, not the future compact operational table yet.
- there is no `unknown_count`.
- there is no `manual_corrections_count`.

### `/api/v3/analytics/quality`

Current fields per row:
- `issue_type`
- `count`
- `percentage`
- `notes`

Current quality buckets:
- `invalid_traceability`
- `missing_evidence`
- `quantity_zero`
- `low_confidence`
- `pending_review`
- `ok`

Current behavior:
- there is no explicit `unknown` bucket.
- the bucket logic is mutually exclusive and priority-based.

## Current formula source

### Current effective source of truth

Today, the formulas are not centralized in one pure application-layer definition.

They are split across:
- `backend/src/application/services/analytics_aggregation_core.py`
- `backend/src/infrastructure/repositories/sql_analytics_repository.py`
- `backend/src/infrastructure/repositories/memory_analytics_repository.py`
- abbreviated comments in `backend/src/application/dto/analytics_dto.py`

### Current recommendation for Phase 2

The single source of truth for formulas should move to the application layer, not frontend code and not duplicated repository SQL.

Recommended target:
- application-layer analytics metric definitions and aggregation helpers under `backend/src/application/services/`
- repositories should fetch raw facts or pre-aggregated facts required by those formulas
- API routes should keep mapping only
- frontend should consume backend-computed metrics and never derive KPI formulas itself

`analytics_aggregation_core.py` is the closest existing layer to grow into that role.

## Ambiguities and gaps found

### 1. Date filtering is not semantically consistent across analytics blocks

Current behavior mixes different time semantics:
- summary review rates use `review_actions.created_at`
- summary processing success uses `inventory_jobs.updated_at`
- invalid traceability in summary ignores date and uses current position state in entity scope
- inventory performance mixes current position state with date-filtered review/job metrics
- aisle issues and quality patterns are effectively current-state snapshots, not time-window analytics

Impact:
- two widgets filtered by the same dates are not measuring the same temporal concept
- frontend cannot explain scope consistently

### 2. `manual_correction_rate` currently measures actions, not resolved positions

Current definition:
- corrections / settling actions

This means:
- one position with multiple review actions can affect the metric multiple times
- the metric is action-volume based, not result-resolution based

This is acceptable for the current implementation, but it is not the clearest operational KPI for the redesigned dashboard.

### 3. `review_rate` and `manual_correction_rate` use different denominator models

Current behavior:
- `review_rate` is reviewed positions / total positions
- `manual_correction_rate` is correction actions / settling actions

Impact:
- the current inventory table mixes position-based and action-based rates side by side
- users can incorrectly assume the rates are directly comparable

### 4. `unknown` is not a first-class persisted review outcome today

Current codebase facts:
- `ReviewActionType` has:
  - `confirm`
  - `update_quantity`
  - `update_sku`
  - `delete_position`
- there is no `mark_unknown` / `set_unknown` review action
- analytics payloads have no `unknown_*` fields
- `PositionStatus` has no `unknown` final state
- `ProductRecord.qty_source` can be `"unknown"`, but that only describes quantity provenance, not final operator resolution
- canonical quantity also exposes `qty_source="unknown"`, but that is still quantity-level, not review-outcome-level

Conclusion:
- current backend data does not support a trustworthy KPI for "final unknown resolution" yet
- Phase 2 needs a persisted unknown-resolution signal before `unknown_rate` can be computed reliably

### 5. `manual correction` and broader `manual intervention` are not separated at the contract level

The plan is correct to separate them.

Current code supports:
- manual corrections:
  - `update_quantity`
  - `update_sku`
- manual interventions already persisted:
  - `confirm`
  - `update_quantity`
  - `update_sku`
  - `delete_position`

Missing for the future breakdown:
- explicit unknown intervention category
- possibly explicit invalid category if that remains distinct from delete in the business flow

### 6. `processing_success_rate` is job-based, not position-based

This is not wrong, but it must remain explicit.

Current definition:
- succeeded aisle jobs / (succeeded + failed aisle jobs)

Implication:
- it measures pipeline execution success, not review quality or result validity

### 7. `average_review_time_seconds` is defined, but its business wording needs tightening

Current implementation:
- average of first settling action timestamp minus `position.created_at`

This means:
- it is not "time from pending review to final resolution"
- it is "time from position creation to first settling action in period"

This is usable, but the name and tooltip for the future dashboard should reflect that exact behavior unless the persistence model changes.

### 8. Quality patterns do not yet include `unknown`

Current bucket list omits `unknown`.
The Phase 1 plan explicitly requires an `unknown` quality pattern in the future dashboard.

### 9. Current inventory/aisle filters are structurally present, but not yet semantically homogeneous

Current API already accepts:
- `date_from`
- `date_to`
- `inventory_id`
- `aisle_id`

And validates:
- `aisle_id` belongs to `inventory_id` when both are present

However, "consistent filters across all analytics data" is still not true because the date semantics differ by block.

## Proposed formulas

These formulas are the recommended target for Phase 2.

### Scope definitions

Use these shared scope counts in the backend payload:

- `total_positions_in_scope`
  - count of non-deleted positions after applying inventory and aisle scope
  - date filter handling must be explicitly defined per Phase 2 metric family, not inferred ad hoc

- `processed_positions_count`
  - count of non-deleted positions considered operationally processed in scope
  - recommended current rule:
    - `status in {reviewed, corrected}`
    - or `status = detected` and `needs_review = false`

- `reviewed_positions_count`
  - count of unique positions with at least one settling review action in scope
  - settling action types:
    - `confirm`
    - `update_quantity`
    - `update_sku`
  - excludes `delete_position`
  - future unknown action should be included once it exists as an explicit resolution action

### 1. `auto_acceptance_rate`

Definition:
- proportion of reviewed positions that were resolved without manual correction

Recommended formula:
- `auto_acceptance_rate = auto_accepted_positions_count / reviewed_positions_count`

Where:
- `auto_accepted_positions_count`
  - unique positions whose terminal resolution category is `confirmed_without_correction`

Denominator:
- `reviewed_positions_count`

Inclusions:
- positions with an explicit final review resolution in scope

Exclusions:
- deleted positions
- positions without a review resolution in scope
- positions with quantity or SKU corrections
- future `unknown` resolutions

Implementation note:
- current code approximates this as `confirm_count / settling_action_count`
- Phase 2 should move to unique-position terminal resolution semantics

### 2. `manual_correction_rate`

Decision:
- this metric should include only SKU and quantity corrections
- it should not include confirm, delete, invalid, or unknown

Recommended formula:
- `manual_correction_rate = manually_corrected_positions_count / reviewed_positions_count`

Where:
- `manually_corrected_positions_count`
  - unique positions whose terminal manual resolution includes:
    - `update_quantity`
    - `update_sku`

Denominator:
- `reviewed_positions_count`

Inclusions:
- quantity corrections
- SKU corrections

Exclusions:
- confirm without correction
- delete
- invalid-only classification if modeled separately
- future unknown resolution

Rationale:
- keeps "correction" narrower than "manual intervention"
- aligns with the recommendation in `Re factor metrics.md`

### 3. `unknown_rate`

Decision:
- define `unknown` as final unknown state, not merely unresolved quantity and not merely missing SKU
- this must be a persisted operational resolution concept, not inferred from `qty_source="unknown"`

Recommended formula:
- `unknown_rate = unknown_positions_count / reviewed_positions_count`

Where:
- `unknown_positions_count`
  - unique positions whose terminal review resolution is `unknown`

Denominator:
- `reviewed_positions_count`

Inclusions:
- positions explicitly resolved to final unknown state

Exclusions:
- positions that merely have:
  - `needs_review = true`
  - missing evidence
  - unresolved SKU
  - `qty_source="unknown"` without final unknown resolution

Current blocker:
- there is no persisted unknown-resolution signal today

Phase 2 requirement:
- add a durable backend field or review action category that represents final unknown resolution

### 4. `processing_success_rate`

Definition:
- proportion of terminal aisle jobs that succeeded

Formula:
- `processing_success_rate = succeeded_aisle_jobs_count / terminal_aisle_jobs_count`

Where:
- `terminal_aisle_jobs_count = succeeded_aisle_jobs_count + failed_aisle_jobs_count`

Denominator:
- terminal aisle jobs in scope

Inclusions:
- `inventory_jobs.target_type = aisle`
- `status in {succeeded, failed}`

Exclusions:
- queued / running / cancelled / non-terminal jobs

Time scope:
- job `updated_at` in filter range

### 5. `average_review_time_minutes`

Definition:
- average elapsed time from position creation to first settling review action

Recommended formula:
- `average_review_time_minutes = avg((first_settling_action_at - position.created_at) in minutes)`

Denominator:
- unique positions with a first settling action in scope

Inclusions:
- first action among:
  - `confirm`
  - `update_quantity`
  - `update_sku`
- future unknown action should also be included once modeled as a review resolution

Exclusions:
- deleted-only actions
- positions without a settling action in scope
- negative lags

Current note:
- current backend exposes seconds; future summary contract should expose minutes for UI readability

### 6. `invalid_traceability_rate`

Definition:
- proportion of in-scope non-deleted positions whose canonical traceability resolves to invalid

Recommended formula:
- `invalid_traceability_rate = invalid_traceability_positions_count / total_positions_in_scope`

Denominator:
- `total_positions_in_scope`

Inclusions:
- non-deleted positions in scope
- canonical traceability status resolved as `invalid`

Exclusions:
- deleted positions

Time-scope note:
- if Phase 2 wants strict date consistency, this metric needs an explicit date-scope rule
- until then, it should be documented as a current-state metric over entity scope

## Decision: manual correction vs manual intervention

### Manual correction

Use only:
- `update_quantity`
- `update_sku`

### Manual intervention

Use the broader operator action family:
- `confirm`
- `update_quantity`
- `update_sku`
- `delete`
- `unknown`
- `invalid` if represented separately from delete in the final review model

Conclusion:
- `manual_correction_rate` must stay narrow
- the broader operational picture belongs in `manual_intervention_breakdown`

## Decision: what counts as `unknown`

Recommended final definition:
- `unknown` means the final operator-facing resolution of a position is unknown

Not sufficient on its own:
- `needs_review = true`
- unresolved position with no action yet
- missing evidence
- absent SKU
- `qty_source = "unknown"` on `ProductRecord`
- canonical quantity source `unknown`

Reason:
- the dashboard KPI needs a terminal business outcome, not a technical inference state

Required Phase 2 backend change:
- persist an explicit unknown terminal resolution signal

## Target contracts for Phase 2

These are proposed target payloads only. They should not replace current contracts in Phase 1.

### Summary KPI response

```json
{
  "auto_acceptance_rate": 0.64,
  "manual_correction_rate": 0.18,
  "unknown_rate": 0.07,
  "processing_success_rate": 0.93,
  "average_review_time_minutes": 12.4,
  "invalid_traceability_rate": 0.09,
  "unknown_count": 38,
  "processed_positions_count": 307,
  "reviewed_positions_count": 211,
  "total_positions_in_scope": 412,
  "notes": []
}
```

### Inventory performance row

```json
{
  "inventory_id": "inv-1",
  "inventory_name": "Inventory A",
  "created_at": "2026-03-01T10:00:00Z",
  "aisles_count": 12,
  "positions_count": 412,
  "processed_count": 307,
  "auto_acceptance_rate": 0.64,
  "manual_correction_rate": 0.18,
  "unknown_rate": 0.07,
  "invalid_traceability_rate": 0.09,
  "avg_confidence": 0.88,
  "processing_success_rate": 0.93,
  "average_review_time_minutes": 12.4
}
```

### Future manual intervention breakdown

```json
{
  "reviewed_positions_count": 211,
  "items": [
    { "category": "confirmed", "count": 135, "percentage": 0.64 },
    { "category": "qty_corrected", "count": 21, "percentage": 0.10 },
    { "category": "sku_corrected", "count": 17, "percentage": 0.08 },
    { "category": "invalid", "count": 8, "percentage": 0.04 },
    { "category": "unknown", "count": 15, "percentage": 0.07 },
    { "category": "deleted", "count": 15, "percentage": 0.07 }
  ]
}
```

Notes:
- percentages should use one explicit denominator, recommended:
  - `reviewed_positions_count`
- categories should be mutually exclusive terminal resolution categories for clarity

### Future aisle attention row

```json
{
  "aisle_id": "aisle-1",
  "aisle_code": "A-01",
  "inventory_id": "inv-1",
  "inventory_name": "Inventory A",
  "positions_count": 48,
  "pending_review_count": 9,
  "unknown_count": 3,
  "invalid_traceability_count": 4,
  "manual_corrections_count": 6
}
```

### Future quality patterns including unknown

```json
{
  "items": [
    { "issue_type": "Unknown", "count": 38, "percentage": 0.12, "notes": "Final unknown resolution" },
    { "issue_type": "Pending review", "count": 27, "percentage": 0.09, "notes": "needs_review flag set" },
    { "issue_type": "Invalid traceability", "count": 19, "percentage": 0.06, "notes": "Canonical traceability status invalid" },
    { "issue_type": "Missing evidence", "count": 12, "percentage": 0.04, "notes": "No primary evidence id" },
    { "issue_type": "Zero quantity", "count": 11, "percentage": 0.04, "notes": "Canonical final quantity resolved as 0" },
    { "issue_type": "Low confidence", "count": 10, "percentage": 0.03, "notes": "Below low confidence threshold" },
    { "issue_type": "No primary issue", "count": 295, "percentage": 0.72, "notes": "Did not match higher-priority buckets" }
  ]
}
```

## Required contract changes for Phase 2

### Summary

Add:
- `unknown_rate`
- `unknown_count`
- `processed_positions_count`
- `reviewed_positions_count`
- `total_positions_in_scope`
- `average_review_time_minutes`

Deprecate from primary dashboard use:
- `settling_actions_per_day`

### Inventory performance

Rename or replace:
- `total_aisles` -> `aisles_count`
- `total_positions` -> `positions_count`
- `processed_positions` -> `processed_count`
- `review_rate` -> remove from the main table unless explicitly redefined
- `correction_rate` -> `manual_correction_rate`

Add:
- `auto_acceptance_rate`
- `unknown_rate`
- `average_review_time_minutes`

### Aisles requiring attention

Replace current quality-heavy row with compact operational fields:
- `positions_count`
- `pending_review_count`
- `unknown_count`
- `invalid_traceability_count`
- `manual_corrections_count`

### Quality patterns

Add explicit:
- `Unknown`

### Manual intervention breakdown

Add a new endpoint or extend analytics scope with a dedicated payload for:
- confirmed
- qty corrected
- sku corrected
- invalid
- unknown
- deleted

## Naming decisions

Recommended names for the next phase:
- keep `auto_acceptance_rate`
- keep `manual_correction_rate`
- add `unknown_rate`
- keep `processing_success_rate`
- expose `average_review_time_minutes`
- keep `invalid_traceability_rate`
- prefer `Aisles requiring attention` over `Aisles with review pressure`
- avoid `review_rate` unless it is explicitly redefined and documented

## Risks for Phase 2

### Unknown persistence gap

There is currently no durable final unknown review outcome in analytics-ready form.

### Formula duplication gap

SQL and memory repositories duplicate KPI logic today. If Phase 2 expands payloads without centralizing formulas, drift risk will increase.

### Date-scope inconsistency

Phase 2 must choose one documented time semantics per metric family, otherwise filters will remain confusing even with better payloads.

## Recommended next step for Phase 2

1. Introduce a centralized application-layer analytics metric definition module, with repositories reduced to fact gathering.
2. Add the persisted unknown-resolution concept required for `unknown_rate` and `manual_intervention_breakdown`.
3. Expand summary and inventory-performance contracts with the documented Phase 2 fields.
4. Add a dedicated manual-intervention breakdown payload.
5. Make date, inventory, and aisle scope semantics explicit and consistent across all analytics endpoints.
