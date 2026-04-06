# Technical Audit: Multi-Provider & Benchmarking Architecture (Final)

This audit provides an implementation-ready assessment of the Dinamic Inventory (v3) architecture. It defines the technical blockers and necessary structural changes to support multi-provider, multi-model, and multi-prompt benchmarking with full traceability and operational reliability.

---

## 1. Findings Categorization

| Finding | Status | Evidence Location | Confidence |
| :--- | :--- | :--- | :--- |
| **Single-Aisle Persistence Lock** | Confirmed | `src/database/schema.sql`: `positions` table | 100% |
| **API Parameter Absence** | Confirmed | `src/api/routes/v3/aisles.py`: `start_aisle_processing` | 100% |
| **Position-to-Job Blindness** | Confirmed | `src/infrastructure/pipeline/v3_report_mapper.py` | 100% |
| **Knowledge Transfer Loss** | Probable | `src/application/use_cases/persist_aisle_result.py` | 90% (Inferred) |
| **Merge Engine Cross-Pollination** | Confirmed | `src/application/use_cases/run_aisle_merge.py` | 100% |
| **Export SKU Duplication** | Confirmed | `src/application/use_cases/export_inventory_results.py` | 100% |

---

## 2. Persistence Impact Matrix

| Table/Entity | Current Scope | Current Role | Blocker for Multi-Provider? | Recommended Direction | Severity |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `inventory_jobs` | Aisle / Inv | Execution metadata tracker. | No. | Add `provider`, `model`, `prompt_key` columns. | Low |
| `aisles` | Inventory | Operational status owner. | No. | Add `operational_job_id` pointer. | Low |
| `positions` | Aisle | Primary result storage. | **Yes**. | Add `job_id` FK; remove blind aisle scoping. | **Critical** |
| `product_records` | Position | SKU-level data. | Indirectly. | Remains tied to Position id. | Medium |
| `evidences` | Position | Crop/artifact mapping. | Indirectly. | Remains tied to Position id. | Medium |
| `review_actions` | Position | Operator corrections. | **Yes**. | Job context required for historical tracking. | **High** |
| `raw_labels` | Aisle | Merge engine input. | **Yes**. | Add `job_id` to prevent cross-model merging. | **High** |
| `normalized_labels`| Aisle | Merge engine output. | **Yes**. | Scope by `job_id`. | Medium |
| `final_count_records`| Aisle | Consolidated quantity. | **Yes**. | Scope by `job_id`. | Medium |

---

## 3. API Impact Assessment

### Position & Result Endpoints
- **Position Detail** (`GET /positions/{id}`): Currently resolves the "representative" position for an aisle. Must be updated to ensure `position_id` remains globally unique (via UUID) but the route should support an optional `job_id` for context-aware breadcrumbs.
  - *Symbol*: `src.api.routes.v3.positions.get_position_detail`
- **Aisle Processing Status** (`GET /aisles/{id}/status`): Currently returns a single `latest_job`. Must be evolved into a list of `recent_jobs` with distinct variant metadata.
  - *Symbol*: `src.api.routes.v3.aisles.get_aisle_processing_status`

### Merge & Consolidation
- **Merge Calculation** (`POST /aisles/{id}/merge`): Currently pulls all `raw_labels` for an `aisle_id`. **Major Blocker**: Will merge labels from different models. Must accept a `job_id` to isolate inputs.
  - *Symbol*: `src.application.use_cases.run_aisle_merge.RunAisleMergeUseCase`
- **Merge Results** (`GET /aisles/{id}/merge-results`): Currently returns the latest "global" consolidated counts. Must be scoped by `job_id`.
  - *Symbol*: `src.api.routes.v3.aisles.get_aisle_merge_results`

### Export & Analytics
- **CSV Export** (`GET /inventories/{id}/export`): Currently fetches all `positions` for an inventory. Multi-model runs will cause SKU/Aisle row duplication, breaking ERP integrations.
  - *Symbol*: `src.application.use_cases.export_inventory_results.ExportInventoryResultsUseCase`
- **Metrics** (`GET /api/v3/analytics/summary`): Aggregates results across a time/scope window. Without `job_id` filtering, KPIs (e.g., Confidence, Success Rate) will be skewed by benchmark noise.
  - *Symbol*: `src.api.routes.v3.analytics_api.analytics_summary`

---

## 4. Review Model Analysis

### Operational Scoping
Reviews should primarily apply to the **Operational Job**. A benchmark run is "temporary" until promoted.

### Promotion & Knowledge Transfer
- **What happens on Promotion?**: When a benchmark job is promoted, its `positions` become the authoritative set.
- **Historical Correction Preservation**: This is the "Knowledge Transfer" problem. If Model A's position (UUID: 1) is reviewed, and Model B runs (creating UUID: 2), the review is lost.
- **Recommendation**: `review_actions` should remain `position_id` scoped for audit integrity, but a **Position Mapping Service** should be introduced to "re-apply" historical corrections to new model runs if they detect the same `position_code` or `internal_code` in the same visual location.

### Scoping of `review_actions`
`review_actions` do not need a direct `job_id` if their parent `positions` are correctly job-scoped, but the **Review History UI** will need a `job_id` filter to prevent showing an operator's corrections for Model A while they are reviewing Model B.

---

## 5. Backend Coupling Inventory (Strengthened)

| File Path | Symbol | Behavior & Evidence | Blocker |
| :--- | :--- | :--- | :--- |
| `src/infrastructure/pipeline/v3_job_executor.py` | `V3JobExecutor.execute` | Orchestrates a single `HybridInventoryPipeline` pass with global settings. | No multi-config support. |
| `src/pipeline/hybrid_inventory_pipeline.py` | `HybridInventoryPipeline` | Constructor defaults to `GeminiAnalysisProvider`. | Hardcoded provider DI. |
| `src/infrastructure/pipeline/v3_report_mapper.py` | `map_hybrid_report_to_domain` | Generates new UUIDs for every position without storing the originating `job_id`. | Prevents result-to-run traceability. |
| `src/application/use_cases/persist_aisle_result.py` | `PersistAisleResultUseCase` | Blindly saves positions to `PositionRepository.save()`. | Causes data collision in `positions` table. |

---

## 6. Definition of Done (DoD) & Testing Expectations

### Repository Level
- [ ] Schema migration adding `job_id` to `positions`, `raw_labels`, `normalized_labels`.
- [ ] Repository tests for `SqlPositionRepository` validating that `list_by_aisle(job_id=...)` isolates results.

### API Level
- [ ] `POST /process` accepts `provider`, `model`, `prompt_variant`.
- [ ] `GET /positions` responds to `job_id` filter.
- [ ] CSV Export tests validating no SKU duplication when 2 models have run for the same inventory.

### Frontend Level
- [ ] `TanStack Query` keys updated to include `jobId` for `positions` cache.
- [ ] Benchmarking UI dialog for multi-selection.
- [ ] Result Table variant switcher.

### Legacy Compatibility
- [ ] Jobs with `null` `job_id` (pre-migration) must be resolved as the "Default/Operational" set for backward compatibility.

---

## 7. Recommended First Implementation Slice

**"The Traceable Persistence Slice"**

1.  **Schema**: Add `job_id` FK to the `positions` table.
2.  **Mapper**: Update `map_hybrid_report_to_domain` to accept and set the `job_id` on every `Position` and `RawLabel`.
3.  **Repository**: Update `PositionRepository` to filter by `job_id`.
4.  **Integration**: Ensure that after a job finishes, the UI still shows "the latest" set by passing the `latest_job_id` to the existing list API.

*Rationale*: This secures the data layer first, preventing "Position Explosion" and enabling benchmarking storage immediately, even before the UI and multi-provider selection are fully built.
