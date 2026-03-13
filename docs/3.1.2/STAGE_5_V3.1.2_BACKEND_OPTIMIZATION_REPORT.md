# STAGE_5_V3.1.2_BACKEND_OPTIMIZATION_REPORT.md

## 1. Summary

Stage 5 is a **focused backend optimization pass** for Dinamic Inventory v3.1.2 after v3 API consolidation (Stage 3) and DB normalization (Stage 4). The v3 route surface is now the only supported API, and `inventory_jobs` is the normalized job table. This stage aims to improve performance and maintainability in high-value paths without changing the domain or reintroducing legacy v1 behavior.

After re-auditing the v3 routes, schemas, repositories, and frontend usage, the single concrete optimization implemented is a **traceability enrichment cache** in the v3 shared mapping layer for positions. This avoids repeatedly reading the same `hybrid_report.json` file when listing or viewing many positions from the same job, reducing I/O and CPU cost without changing response contracts. Other v3 endpoints were explicitly reviewed and deemed acceptable as-is; broader contract or query changes were intentionally deferred to keep v3.1.2 low-risk.

---

## 2. Optimization matrix

Endpoint-level assessment across v3 routes (`inventories`, `aisles`, `assets`, `positions`, `reviews`) and corresponding frontend usage.

| Endpoint | Current purpose | Consumer | Issue type | Assessment / Proposed action |
|---------|------------------|----------|------------|------------------------------|
| `GET /api/v3/inventories` | List inventories (id, name, status, created_at) | Frontend `getInventories` | Acceptable as-is | Lightweight summary list; UI uses all fields via `Inventory`. No overfetch risk. |
| `GET /api/v3/inventories/{id}` | Inventory detail | Frontend `getInventory` | Acceptable as-is | Same shape as list item; no heavier detail needed at this stage. |
| `GET /api/v3/inventories/{id}/metrics` | Inventory metrics over positions | Frontend `getInventoryMetrics` | Acceptable as-is | Numeric metrics only; used directly in UI; no obvious duplication. |
| `POST /api/v3/inventories` | Create inventory | Frontend `createInventory` | Acceptable as-is | Returns `InventoryResponse`; minimal and correct. |
| `GET /api/v3/inventories/{inv}/aisles` | List aisles + latest job | Frontend `getAisles` | Acceptable as-is | Summary model (`AisleResponse` with optional `latest_job`). Uses `get_latest_by_targets` in use case to avoid N+1. No change. |
| `POST /api/v3/inventories/{inv}/aisles` | Create aisle | Frontend `createAisle` | Acceptable as-is | Returns single `AisleResponse`. |
| `POST /api/v3/inventories/{inv}/aisles/{aisle}/process` | Start aisle processing, returns job_id | Frontend `startAisleProcessing` | Acceptable as-is | Minimal payload `job_id`; no optimization needed. |
| `GET /api/v3/inventories/{inv}/aisles/{aisle}/status` | Aisle status + latest job summary | Frontend `getAisleStatus` | Acceptable as-is | Uses `ListAislesWithStatusUseCase` under the hood; returns `AisleStatusResponse` with nested aisle and job summary. No waste identified. |
| `GET /api/v3/inventories/{inv}/aisles/{aisle}/jobs/{job}/execution-log` | Structured execution log for a job | Frontend `getExecutionLog` | Acceptable as-is | Reads execution log once from filesystem; returns only events. No overfetch. |
| `POST /api/v3/inventories/{inv}/aisles/{aisle}/assets` | Upload assets to aisle | Frontend `uploadAisleAssets` | Acceptable as-is | Returns `UploadAisleAssetsResponse` with `assets: SourceAssetSummary[]`. Extra `storage_path` is marked in types as reserved; kept. |
| `GET /api/v3/inventories/{inv}/aisles/{aisle}/assets` | List assets | Frontend `getAisleAssets` | Acceptable as-is | Summary fields only; used by UI for asset listing. |
| `GET /api/v3/inventories/{inv}/aisles/{aisle}/assets/{asset}/file` | Serve asset file / normalized preview | Frontend `getReferenceImageFileUrl` | Acceptable as-is | Reads asset list then finds one asset; number of assets per aisle is modest. No change in this stage. |
| `GET /api/v3/inventories/{inv}/aisles/{aisle}/positions` | List positions (results) for an aisle | Frontend `getAislePositions` → `useAislePositions` → `useResultSummaries` | **Performance (I/O)** | Summary-only contract (`PositionSummaryResponse`), but helper `_enrich_position_traceability_from_report` previously read `hybrid_report.json` once per position with `entity_uid`. **Optimized:** added in-process cache for traceability enrichment to avoid repeated file loads per job. No contract change. |
| `GET /api/v3/inventories/{inv}/aisles/{aisle}/positions/{pos}` | Position detail (summary + evidences + review_actions) | Frontend `getPositionDetail` → `usePositionDetail` → `useResultDetail` | Acceptable as-is | Uses same summary DTO as list plus evidences and review history. Frontend relies on `detected_summary_json`, `sku`, `detected_quantity`, `corrected_quantity`, traceability fields. Kept unchanged. |
| `POST /api/v3/inventories/{inv}/aisles/{aisle}/positions/{pos}/reviews` | Submit review action (confirm / update_quantity / update_sku / delete_position) | Frontend `submitReviewAction` | Acceptable as-is | Centralized handling via shared helpers; consistent exception mapping; no duplication worth changing. |

No endpoints were found that obviously overfetch large nested structures beyond consumer needs; contracts are already split into summary vs detail for positions.

---

## 3. Contract changes

### 3.1 Summary

- **No response contracts were changed** in Stage 5. All v3 schemas under `src/api/schemas/` and the corresponding frontend API DTOs remain structurally identical.
- The optimization work focused on **backend execution behavior** (reducing repeated filesystem reads for traceability enrichment) while keeping the public contracts stable.

### 3.2 Fields kept vs removed vs deferred

Based on inspection of backend schemas and frontend usage (`frontend/src/api/types/*.ts`, `features/results` mappers/hooks), fields were categorized as follows:

- **Kept (actively used or clearly justified):**
  - `InventoryResponse`: `id`, `name`, `status`, `created_at` — all used by the inventories UI.
  - `AisleResponse`: all fields including `latest_job` (frontend uses latest job status and error_message for status display).
  - `AisleStatusResponse` / `JobSummary`: used by status polling; all fields retained.
  - `SourceAssetSummary`: all fields; `storage_path` is reserved for future evidence/media views and documented as such in the frontend types.
  - `PositionSummaryResponse`: all fields — `sku`, `detected_quantity`, `corrected_quantity`, `traceability_status`, `source_image_id`, `source_image_original_filename`, `has_evidence`, and `detected_summary_json` are consumed (directly or via mappers) by the results UI.
  - `PositionDetailResponse`: `position`, `evidences`, `review_actions` — all used by `mapPositionDetailToResultDetail`.
  - `ReviewActionRequest`: all fields; validation is delegated to shared handlers.

- **Potentially redundant but intentionally deferred (documented in Stage 1):**
  - `SourceAssetSummary.storage_path`: not used by current UI but reserved; kept.
  - `PositionSummaryResponse.primary_evidence_id` vs `has_evidence`: front-end prefers `has_evidence` but still falls back to checking `primary_evidence_id`. Both kept.
  - `detected_summary_json` on `PositionSummaryResponse`: used by result mappers for traceability fallback; retained for backward compatibility.

- **Removed:**
  - None in Stage 5. No fields were deleted or renamed.

This respects the Stage 5 rule to avoid speculative contract tightening without strong evidence and consumer updates.

---

## 4. Duplication reductions

### 4.1 Shared mapping and review handling

Stage 3 already centralized a significant amount of v3 mapping and error handling in `src/api/routes/v3/shared.py`:
- `inventory_to_response`, `aisle_to_response`, `status_response_from_result`, `asset_to_response`, `position_to_summary`, `evidence_to_response`, `review_to_response`.
- Review helpers `handle_confirm`, `handle_update_quantity`, `handle_update_sku`, `handle_delete_position` and `review_exception_to_http`.

Stage 5 validated that:
- v3 routes (`inventories.py`, `aisles.py`, `assets.py`, `positions.py`, `reviews.py`) consistently use these shared helpers.
- There is no significant remaining duplication in response mapping or exception-to-HTTP mapping worth abstracting further.

**Action:** No new abstractions were introduced. The existing shared helpers are considered the right level of consolidation; additional layers would risk over-abstracting without clear benefit.

---

## 5. Query/performance improvements

### 5.1 Position list vs detail (Focus area A) — traceability enrichment cache

**Context:**
- **List endpoint:** `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` uses `ListAislePositionsUseCase` → `PositionRepository.list_by_aisle[_query]` and returns `PositionListResponse` using `position_to_summary`.
- **Detail endpoint:** `GET /.../positions/{position_id}` uses `GetPositionDetailUseCase` and returns `PositionDetailResponse` (summary + evidences + review_actions), again via `position_to_summary` and `evidence_to_response`/`review_to_response`.

**Existing behavior:**
- Summary vs detail is already well-separated: list returns only summary per position; detail returns that summary plus evidences and history.
- The SQL repository (`SqlPositionRepository`) already supports filtered/paginated listing, avoiding in-memory filtering.

**Identified inefficiency:**
- `position_to_summary` enriches traceability fields (`source_image_id`, `traceability_status`, `source_image_original_filename`) by reading `hybrid_report.json` via `_enrich_position_traceability_from_report` when they are missing in `detected_summary_json`.
- `_enrich_position_traceability_from_report` previously opened and parsed `hybrid_report.json` **once per position** sharing the same job, even though the file is identical for all positions in that job.

**Optimization implemented:**
- A **simple, bounded in-process cache** was added in `src/api/routes/v3/shared.py`:
  - `_TRACEABILITY_CACHE: Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]]` keyed by `entity_uid` from `detected_summary_json`.
  - `_TRACEABILITY_REPORTS_LOADED: Set[str]` keyed by `job_id`.
  - `_MAX_TRACEABILITY_JOBS` / `_MAX_TRACEABILITY_ENTITIES` and `_maybe_evict_traceability_cache()` to clear the cache when it grows beyond small thresholds (best-effort bound).
- New behavior in `_enrich_position_traceability_from_report`:
  1. Validate and extract `entity_uid` from `detected_summary_json`.
  2. If `entity_uid` is in `_TRACEABILITY_CACHE`, return the cached triple.
  3. Split `entity_uid` into `job_id` and suffix. If `job_id` is already in `_TRACEABILITY_REPORTS_LOADED` and the entity is not cached, return `(None, None, None)` without touching the filesystem again.
  4. Otherwise, load `hybrid_report.json` once for that `job_id`, iterate all entities, and populate `_TRACEABILITY_CACHE` for each `entity_uid` found (normalizing string values when present).
  5. Mark the job as loaded in `_TRACEABILITY_REPORTS_LOADED`, invoke `_maybe_evict_traceability_cache()` to keep the cache bounded, and return the triple for the requested `entity_uid` (or `(None, None, None)` if absent).

**Impact:**
- For a job with many positions, the report file is read **once per process per job_id** instead of once per position (while the process cache is warm).
- The list and detail endpoints both benefit, since both use `position_to_summary` and hence the same enrichment function.
- Cache is **best-effort and bounded**: if many distinct jobs/entities are inspected in one long-lived process, the cache is cleared rather than growing unbounded.
- No changes to SQL queries, response contracts, or domain behavior; this is a pure I/O and CPU optimization.

### 5.2 Aisle status / job execution visibility (Focus area B)

Assessment of:
- `GET /aisles/{aisle_id}/status` (AisleStatusResponse)
- `GET /aisles/{aisle_id}/jobs/{job_id}/execution-log`

Findings:
- `ListAislesWithStatusUseCase` already batches latest job lookups with `JobRepository.get_latest_by_targets`, avoiding N+1 queries.
- Execution log endpoint reads a single `run_dir` per request via `read_execution_log`; no repeated work.
- Response contracts are minimal (aisle summary + job summary; execution events list). No evident overfetch.

**Action:** No changes; endpoints considered efficient and clear.

### 5.3 Shared mapping layer (Focus area C)

- The shared mapping layer (`shared.py`) already centralizes mapping and exception logic used across v3 routes.
- No additional duplication or inconsistent shaping was found that justified more abstraction.
- The only change in this layer was the **traceability enrichment cache** described above.

### 5.4 Review action handling (Focus area D)

- Review actions are funneled through a single endpoint and a small set of shared helpers.
- Exception-to-HTTP mapping is centralized in `review_exception_to_http`.
- No branching or validation duplication beyond what is needed for clarity.

**Action:** No changes; the review flow is already concise and maintainable.

---

## 6. Compatibility notes

- **Backend contracts:** No schemas were changed. All v3 Pydantic models (`InventoryResponse`, `AisleResponse`, `ProcessAisleResponse`, `AisleStatusResponse`, `ExecutionLogResponse`, `SourceAssetResponse`, `PositionListResponse`, `PositionDetailResponse`, `ReviewActionRequest`) remain identical.
- **Frontend types:** `frontend/src/api/types/*.ts` were not changed. Existing mappers/hook layers (`features/results`, `hooks/usePositions.ts`) continue to work without modification.
- **Behavioral semantics:** The enrichment change only affects how often traceability fields are *computed*; it does not change the values returned when a `hybrid_report.json` is present. When no report exists or entity is not present, the behavior is still to return `None`/`null` for those fields.
- **Tests:** No test expectations were changed. Existing frontend tests for result mappers (`frontend/tests/resultMappers.test.ts`) remain valid because the response shapes are unchanged.

---

## 7. Deferred items

- **Field removal / slimming:** Even though Stage 1 identified some potentially redundant fields (e.g. `SourceAssetSummary.storage_path`, `primary_evidence_id` vs `has_evidence`), they are kept in v3.1.2. Removing or renaming them would require coordinated frontend updates and is better suited for a future versioned contract change.
- **Asset file endpoint efficiency:** `get_aisle_asset_file` currently uses `ListAisleAssetsUseCase` and then selects a single asset in memory. For large numbers of assets per aisle this could be refined via a dedicated repository method (`get_asset_by_id`), but current usage patterns do not justify the additional plumbing in v3.1.2.
- **Additional caching:** Only traceability enrichment was cached. Other heavy operations (e.g. result report parsing for different flows) could be cached in future stages, preferably with clear lifecycle and instrumentation.

---

## 8. Validation notes

- **API contract vs frontend usage:** For each v3 endpoint, corresponding frontend calls (`frontend/src/api/client.ts`) and mappers/hooks (`features/results`, `hooks/usePositions.ts`) were inspected to confirm which fields are actually consumed. No contract changes were made where consumers relied on a field.
- **Summary vs detail boundaries:** Position list vs detail contracts were checked against Stage 1 findings and frontend result mappers. The boundary is already aligned with the Result-centric model (summary in list; detail adds evidence and history). No changes beyond the internal enrichment optimization were required.
- **Query behavior:** `ListAislesWithStatusUseCase` and `SqlPositionRepository` were inspected to confirm that:
  - Aisle listing with status uses a batched `get_latest_by_targets` call (no API-layer N+1).
  - Position listing uses a single SQL query with optional pagination and filters.
- **Traceability cache correctness and lifecycle:** The cache only affects internal enrichment. It:
  - Short-circuits with a cache hit when `entity_uid` is known.
  - Falls back to the previous behavior when no report or entity is found.
  - Does not change how `position_to_summary` decides to call enrichment (still conditioned on `entity_uid` being present and traceability fields missing).
  - Treats `hybrid_report.json` as immutable for the life of the process (aligned with the pipeline writing it once per job). If a report is regenerated while a process is running, enrichment may use the older contents until the process restarts or the cache is evicted.
  - Can be cleared in tests or one-off scripts via the internal `_reset_traceability_cache_for_tests()` helper to avoid cross-test contamination.
- **Lints and static checks:** Updated modules (`src/api/routes/v3/shared.py`) and inspected frontend/backend files show no new linter errors.

---

**Document version:** 1.1 (corrective pass: clarify Stage 5 scope, cache bounding and assumptions)  
**Stage:** 5 — Backend optimization  
**Date:** 2025-03-06
