# Analytics Phase 2 / Phase 3 Validation

## Scope
This note validates the current analytics implementation against:
- `docs/Re factor metrics.md`
- `docs/analytics_metrics_phase1_audit.md`

This is a validation and gap-analysis pass for:
- Phase 2: backend analytics refactor
- Phase 3: frontend dashboard refactor

Status labels used in this note:
- `complete`
- `partial`
- `missing`
- `blocked`

## Phase 2 validation

### Summary analytics expanded with Phase 2 fields
- Status: `complete`
- Implemented in:
  - `backend/src/api/routes/v3/analytics_api.py`
  - `backend/src/api/schemas/analytics_schemas.py`
  - `backend/src/application/dto/analytics_dto.py`
  - `backend/src/application/services/analytics_aggregation_core.py`
- Verified fields:
  - `average_review_time_minutes`
  - `total_positions_in_scope`
  - `processed_positions_count`
  - `reviewed_positions_count`
- Notes:
  - Legacy fields are also preserved for compatibility:
    - `average_review_time_seconds`
    - `positions_in_scope`
    - `settling_actions_per_day`
    - `settling_actions_count`

### KPI formulas centralized in the application layer
- Status: `partial`
- Centralized pieces exist in:
  - `backend/src/application/services/analytics_aggregation_core.py`
- What is complete:
  - summary KPI math is centralized through:
    - `compute_review_outcome_counts()`
    - `processed_position()`
    - `build_summary_metrics()`
    - `build_inventory_metric_rates()`
    - `compute_manual_intervention_breakdown()`
  - memory and SQL repositories now use these helpers for the main KPI calculations
- Why only partial:
  - repositories still own significant fact gathering and some query-shape-specific aggregation logic
  - `trends`, `quality_patterns`, and `aisle_issues` still include endpoint-specific semantics inside repository implementations
- Fix now or later:
  - later
  - current state is a meaningful improvement and low-risk for Phase 2

### `manual_correction_rate` includes only quantity / SKU corrections
- Status: `complete`
- Implemented in:
  - `backend/src/application/services/analytics_aggregation_core.py`
- Evidence:
  - `correction_action()` only counts:
    - `update_quantity`
    - `update_sku`
  - `compute_review_outcome_counts()` uses that narrow definition
  - `build_summary_metrics()` and `build_inventory_metric_rates()` derive the rate from `manually_corrected_positions_count`

### Inventory performance contract expanded with transitional/new fields
- Status: `complete`
- Implemented in:
  - `backend/src/api/schemas/analytics_schemas.py`
  - `backend/src/api/routes/v3/analytics_api.py`
  - `backend/src/application/dto/analytics_dto.py`
  - both analytics repositories
- New/additive fields present:
  - `aisles_count`
  - `positions_count`
  - `processed_count`
  - `auto_acceptance_rate`
  - `manual_correction_rate`
  - `average_review_time_minutes`
- Transitional/legacy fields preserved:
  - `total_aisles`
  - `total_positions`
  - `processed_positions`
  - `review_rate`
  - `correction_rate`

### `/api/v3/analytics/manual-interventions` exists
- Status: `complete`
- Implemented in:
  - `backend/src/api/routes/v3/analytics_api.py`
  - `backend/src/api/schemas/analytics_schemas.py`
  - `backend/src/application/services/analytics_query_service.py`
  - `backend/src/application/ports/analytics_repository.py`
  - both analytics repositories

### `unknown` is not faked if persistence does not support terminal unknown
- Status: `complete`
- Implemented in:
  - `backend/src/application/services/analytics_aggregation_core.py`
  - `backend/src/api/routes/v3/analytics_api.py`
  - both repositories
- Current behavior:
  - there is no `unknown_rate` or `unknown_count` exposed in summary
  - manual intervention breakdown exposes `unknown` as unavailable instead of synthesizing a value
- Why this is correct:
  - matches the Phase 1 audit decision that `unknown` must be a terminal persisted business outcome, not inferred from `qty_source="unknown"`

### SQL and memory analytics logic meaningfully aligned
- Status: `partial`
- What is aligned:
  - summary KPI definitions
  - inventory performance KPI definitions
  - manual intervention breakdown semantics
  - average review time minutes exposure
- Why only partial:
  - query paths and lower-level aggregation still differ between SQL and in-memory implementations
  - `quality_patterns` and `aisle_issues` remain parallel but not fully abstracted through a shared application-layer fact model
- Fix now or later:
  - later
  - current alignment is sufficient for the main Phase 2 KPI/contract goals

### Tests cover the new analytics behavior
- Status: `partial`
- Implemented tests:
  - `backend/tests/application/test_analytics_phase51.py`
  - `backend/tests/api/test_analytics_api.py`
- What is complete:
  - application/service-level tests cover:
    - centralized KPI helpers
    - processed position logic
    - summary metric building
    - manual intervention breakdown semantics
  - API-level tests exist for:
    - expanded summary shape
    - expanded inventory shape
    - manual interventions endpoint
- Why only partial:
  - API tests exist in repo but depend on `fastapi` availability in the runtime environment
  - they are not guaranteed to execute in every local validation environment
- Fix now or later:
  - later
  - no code issue; this is an environment/dependency validation gap

## Phase 3 validation

### Dashboard no longer renders Review activity / Processing outcomes / Settling actions per day
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
  - `frontend/tests/MetricsPage.test.tsx`

### KPI hierarchy reflects the new product priority
- Status: `partial`
- What is complete:
  - KPI order now prioritizes:
    - auto-acceptance
    - manual correction
    - processing success
    - average review time
    - invalid traceability
  - `unknown` is omitted cleanly when unavailable
- Why only partial:
  - the plan’s ideal six-card hierarchy includes `Unknown rate` as a first-class KPI
  - current implementation cannot render it truthfully because backend/business persistence does not support terminal unknown resolution yet
- Fix now or later:
  - later, once blocked backend support exists

### Inventory performance is promoted above aisle attention
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
- Current layout order:
  - filters
  - KPI cards
  - operational visuals
  - inventory performance
  - quality patterns + aisle attention

### Aisle table is secondary and paginated
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
- Notes:
  - rendered as `Aisles requiring attention`
  - local pagination is enabled
  - it is visually secondary to `Inventory performance`

### Manual intervention breakdown is rendered if backend supports it
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
  - `frontend/src/features/analytics/hooks.ts`
  - `frontend/src/api/client.ts`

### Resolution flow block exists
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
- Notes:
  - implemented as a compact stat-strip style block
  - uses truthful current fields only

### Inventory / aisle filters drive the page coherently
- Status: `partial`
- What is complete:
  - page-level query params are applied to all analytics queries via `useAnalyticsDashboard()`
  - aisle select depends on selected inventory
  - invalid aisle selection is reset when current aisle is not part of the filtered aisle list
  - scope summary line is rendered from current page state + summary response
- Why only partial:
  - inventory filtering still intentionally supports an all-scope state via `All inventories`
  - there is no persisted URL/query-param state for the filter bar
  - Phase 3 plan emphasized real inventory scoping; current page does support true filtering, but still defaults to the global scope
- Fix now or later:
  - later unless product explicitly wants to force inventory selection

### Unknown is shown only if backend truthfully supports it
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
  - `frontend/src/api/types/analytics.ts`
  - `frontend/tests/MetricsPage.test.tsx`
- Current behavior:
  - `Unknown rate` KPI is omitted when `summary.unknown_rate` is absent
  - manual intervention `unknown` category is shown as unavailable when backend marks it unavailable
  - no fake unknown values are rendered

### New backend contracts are consumed cleanly
- Status: `complete`
- Verified in:
  - `frontend/src/api/types/analytics.ts`
  - `frontend/src/api/client.ts`
  - `frontend/src/api/queryKeys.ts`
  - `frontend/src/features/analytics/api.ts`
  - `frontend/src/features/analytics/hooks.ts`
  - `frontend/src/features/analytics/MetricsPage.tsx`
- Notes:
  - additive Phase 2 fields are consumed with clean fallback handling for transitional legacy names

### Layout and labels reflect the operational dashboard direction
- Status: `complete`
- Verified in:
  - `frontend/src/features/analytics/MetricsPage.tsx`
- Notes:
  - title and section copy are more operational
  - `Aisles requiring attention` replaces the old label in the UI

## User-observed items

### `All inventories` still appears in the selector
- Validation result: `partial`
- Current state:
  - yes, the inventory selector still includes `All inventories`
  - implemented in `frontend/src/features/analytics/MetricsPage.tsx`
- Classification:
  - this is `b) intentionally unchanged and acceptable` for the current implementation
  - it is not a bug in the current code path; the page does support true inventory filtering when a specific inventory is selected
- Why not marked fully complete:
  - the Phase 3 plan/problem statement emphasized that inventory needed to behave as a real scope driver
  - the current implementation supports that, but it still also supports an all-scope state, which may continue to feel ambiguous from a product perspective
- Fix now or later:
  - later
  - only change if product decides the page should require explicit inventory selection by default

### `UNKNOWN` is still not identified / counted
- Validation result: `blocked`
- Current state:
  - backend contract readiness: partial
    - UI and DTOs are ready to consume `unknown_rate` if it becomes available
    - manual intervention breakdown explicitly carries unavailable `unknown`
  - UI readiness: complete
    - frontend omits unknown KPI cleanly
    - frontend does not fabricate unknown values
  - actual persisted business support: blocked
    - there is no durable terminal unknown review resolution in the current review model
- Classification:
  - blocked, not incomplete implementation
- Why:
  - current model lacks:
    - explicit unknown review action
    - explicit unknown final position status
    - explicit terminal unknown resolution field
- Fix now or later:
  - later
  - requires domain / persistence work, not a safe validation-pass fix

## Remaining gaps

### Phase 2
- Formula centralization is improved but not absolute.
- SQL and memory repositories are meaningfully aligned for summary/inventory metrics, but not fully unified for all analytics families.
- API test execution still depends on local FastAPI availability.

### Phase 3
- `Unknown rate` KPI cannot appear yet because backend/business support is blocked.
- `Quality patterns` does not currently show explicit `Unknown` because backend does not provide that bucket yet.
- `Inventory performance` does not currently show `Unknown rate` because backend does not provide it.
- `Aisles requiring attention` still renders the truthful current subset, not the future compact contract:
  - no `unknown_count`
  - no `manual_corrections_count` dedicated field

## Blocked items

### Terminal unknown resolution support
- Status: `blocked`
- Blocking reason:
  - current review/domain persistence does not model terminal unknown resolution
- Affected deliverables:
  - `unknown_rate`
  - `unknown_count`
  - explicit unknown inventory performance column
  - explicit unknown aisle attention count
  - explicit unknown quality pattern bucket

### Distinct `invalid` intervention category
- Status: `blocked`
- Blocking reason:
  - current persisted review model does not distinguish `invalid` from `delete_position`
- Affected deliverables:
  - full manual intervention category completeness

## Recommended next step

1. Add a durable terminal unknown resolution concept to the review/domain model.
2. Decide whether `invalid` remains coupled to delete or becomes its own explicit persisted review outcome.
3. Expand backend analytics contracts to include:
   - `unknown_rate`
   - `unknown_count`
   - inventory-level `unknown_rate`
   - aisle-level `unknown_count`
   - quality bucket `Unknown`
4. Once backend support exists, update the frontend to surface:
   - `Unknown rate` KPI
   - `Unknown rate` inventory column
   - `Unknown` quality pattern
   - `Unknown` aisle attention metric
5. If product wants stronger scope discipline, decide whether the page should still allow `All inventories` or require explicit inventory selection by default.
