# Technical Audit: Multi-Provider & Benchmarking Architecture (Final)

**Planning alignment:** extended rules, analytics precision, review MVP stance, and DoD/test matrix — [`multi_provider_planning_revision.md`](./multi_provider_planning_revision.md).

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
| `inventory_jobs` | Aisle / Inv | Execution metadata tracker. | No. | Add indexed `provider_name`, `model_name`, `prompt_key`, `engine_params_json`; add **`prompt_version` and/or rendered prompt snapshot** for long-term comparability (see planning revision). | Low |
| `aisles` | Inventory | Operational status owner. | No. | Add `operational_job_id` pointer. | Low |
| `positions` | Aisle | Primary result storage. | **Yes**. | Add `job_id` FK; remove blind aisle scoping. | **Critical** |
| `product_records` | Position | SKU-level data. | Indirectly. | Remains tied to Position id. | Medium |
| `evidences` | Position | Crop/artifact mapping. | Indirectly. | Remains tied to Position id. | Medium |
| `review_actions` | Position | Operator corrections. | Indirectly (MVP). | **MVP**: remain `position_id`-scoped; editable dataset constrained by `operational_job_id` + position membership. **No `job_id` column required on `review_actions` for MVP.** Optional future FK only if product needs cross-run audit without joining via positions. | Medium |
| `raw_labels` | Aisle | Merge engine input. | **Yes**. | Add `job_id` to prevent cross-model merging. | **High** |
| `normalized_labels`| Aisle | Merge engine output. | **Yes**. | Scope by `job_id`. | Medium |
| `final_count_records`| Aisle | Consolidated quantity. | **Yes**. | Scope by `job_id`. | Medium |

---

## 3. API Impact Assessment

### Evidence, crops, and previews (critical)
Once multiple jobs exist per aisle, **any** endpoint or helper that loads evidence, crops, source assets, or preview images must **not** resolve the target using **implicit “latest job”** heuristics. It must use the **same result context** as positions (explicit `job_id` → `operational_job_id` → legacy `job_id IS NULL`). **MVP** keeps `evidences` job-scoped only via `position_id`, so **position set resolution must happen first** on every read path. See `docs/multi_provider_planning_revision.md` §3.3, §4.1.

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
- **Metrics** (`GET /api/v3/analytics/summary` and related): Aggregates results across a time/scope window. Without **per-aisle** operational vs legacy rules and **exclusion of benchmark jobs at the repository/query layer**, KPIs will be skewed by benchmark noise and **inflate** after multiple runs on the same aisle. Default operational analytics must include only: (1) rows for `job_id = operational_job_id` where set, and (2) `job_id IS NULL` for aisles still legacy. **Benchmark analytics are out of MVP scope.**
  - *Symbol*: `src.api.routes.v3.analytics_api.analytics_summary`

---

## 4. Review Model Analysis

### Operational Scoping
Reviews should primarily apply to the **Operational Job**. A benchmark run is "temporary" until promoted.

### Promotion & Knowledge Transfer
- **What happens on Promotion?**: When a benchmark job is promoted, its `positions` become the authoritative set.
- **Historical Correction Preservation**: This is the "Knowledge Transfer" problem. If Model A's position (UUID: 1) is reviewed, and Model B runs (creating UUID: 2), the review is lost.
- **Recommendation (post-MVP)**: A **Position Mapping Service** (or equivalent) could re-apply historical corrections to new model runs when the same `position_code` or `internal_code` aligns across runs. This is **not** required for MVP; **no automatic correction transfer** in the first rollout.

### Scoping of `review_actions` (MVP — explicit)
- **`review_actions` do not require `job_id` in MVP.** Rows stay keyed by `position_id`; audit integrity is preserved because corrections attach to a stable position row.
- **Editable surface** is enforced by **operational job only**: only positions belonging to `aisles.operational_job_id` are mutable; benchmark positions are read-only at the API/domain layer.
- **Review History UI** must respect the **selected result context** (explicit `job_id`, operational, or legacy) so operators do not mix corrections from one run’s position set with another’s view. That is a **read/filter concern**, not a prerequisite to add `job_id` to `review_actions`.
- **Automatic correction transfer** when promoting or switching runs is a **later feature**, not a prerequisite for multi-provider rollout.

**Alignment note:** Earlier wording suggesting `job_id` on `review_actions` was mandatory for MVP is **rejected**; see `docs/multi_provider_planning_revision.md`.

---

## 5. Backend Coupling Inventory (Strengthened)

| File Path | Symbol | Behavior & Evidence | Blocker |
| :--- | :--- | :--- | :--- |
| `src/infrastructure/pipeline/v3_job_executor.py` | `V3JobExecutor.execute` | Orchestrates a single `HybridInventoryPipeline` pass with global settings. | No multi-config support. |
| `src/pipeline/hybrid_inventory_pipeline.py` | `HybridInventoryPipeline` | Constructor defaults to `HybridGlobalAnalysisStrategy` (provider-neutral; executor from registry). | Default strategy wiring. |
| `src/infrastructure/pipeline/v3_report_mapper.py` | `map_hybrid_report_to_domain` | Generates new UUIDs for every position without storing the originating `job_id`. | Prevents result-to-run traceability. |
| `src/application/use_cases/persist_aisle_result.py` | `PersistAisleResultUseCase` | Blindly saves positions to `PositionRepository.save()`. | Causes data collision in `positions` table. |

---

## 6. Definition of Done (DoD) & Testing Expectations

Authoritative expanded DoD and test matrix: **`docs/multi_provider_planning_revision.md`** (§6–§7). Summary checklist:

### Repository Level
- [ ] Schema migration adding `job_id` to `positions`, `raw_labels`, `normalized_labels` (and related tables per implementation plan).
- [ ] Repository tests: `list_by_aisle(job_id=...)` isolates results; **two runs same aisle, no collision**.
- [ ] **Analytics/repository queries**: default operational scope **excludes benchmark jobs**; **mixed** legacy + operational aisles in one inventory behave per-aisle.

### API Level
- [ ] `POST /process` accepts `provider`, `model`, `prompt_variant` / `prompt_key` (per plan); **one request → one job** (MVP).
- [ ] `GET /positions` (and job-aware reads) respond to **`job_id`** and resolver rules: explicit → operational → legacy.
- [ ] **Evidence / crop / preview / image** endpoints: **no implicit latest-job** behavior; correctness **per selected job** tested.
- [ ] CSV Export: **no duplicate operational rows** after multiple benchmark runs on same aisle.
- [ ] **Review**: benchmark read-only; operational editable only.

### Frontend Level
- [ ] `TanStack Query` keys updated to include `jobId` for `positions` cache.
- [ ] Benchmarking UI dialog for multi-selection.
- [ ] Result Table variant switcher; **KPIs match selected dataset only**.

### Legacy Compatibility
- [ ] Where `operational_job_id` is null, **`job_id IS NULL`** rows resolve as legacy operational set.

### Provider architecture
- [ ] Contract tests; **shared logic** not trapped in vendor-specific classes (see planning revision §1, §6).

---

## 7. Recommended First Implementation Slice

**"The Traceable Persistence Slice"**

1.  **Schema**: Add `job_id` FK to the `positions` table.
2.  **Mapper**: Update `map_hybrid_report_to_domain` to accept and set the `job_id` on every `Position` and `RawLabel`.
3.  **Repository**: Update `PositionRepository` to filter by `job_id`.
4.  **Integration**: Ensure that after a job finishes, the UI still shows "the latest" set by passing the `latest_job_id` to the existing list API.

*Rationale*: This secures the data layer first, preventing "Position Explosion" and enabling benchmarking storage immediately, even before the UI and multi-provider selection are fully built.
