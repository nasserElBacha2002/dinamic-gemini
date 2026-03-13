# AUDIT_STAGE_5_CORRECTIVE_PASS.md

## 1. Verdict

**Approved with observations**

## 2. Summary

The Stage 5 corrective pass successfully hardens the traceability enrichment cache in `shared.py` without changing public API contracts or introducing significant new risk. The cache is now explicitly bounded, its assumptions about `hybrid_report.json` immutability are documented, and a minimal test-reset hook exists. The scope remained focused on the intended optimization, with reports updated to honestly describe the narrow but valuable change. Remaining risks are low and mostly related to the inherently best-effort nature of the enrichment.

## 3. What was reviewed

- `src/api/routes/v3/shared.py`
  - Global cache definitions and helpers:
    - `_TRACEABILITY_CACHE`
    - `_TRACEABILITY_REPORTS_LOADED`
    - `_MAX_TRACEABILITY_JOBS`
    - `_MAX_TRACEABILITY_ENTITIES`
    - `_maybe_evict_traceability_cache()`
    - `_reset_traceability_cache_for_tests()`
  - `_enrich_position_traceability_from_report()`
  - `position_to_summary()`
- Documentation:
  - `docs/3.1.2/STAGE_5_V3.1.2_BACKEND_OPTIMIZATION_REPORT.md` (version 1.1)
  - `docs/3.1.2/STAGE_5_V3.1.2_CORRECTIVE_PASS_REPORT.md`

## 4. Findings

### 4.1 Correctness

- **Finding C1 (Low)**  
  **Severity:** Low  
  **Explanation:** The enrichment logic preserves previous behavior while adding caching and bounds. For a given `entity_uid`, when `hybrid_report.json` exists and contains a matching entity, the returned `(source_image_id, traceability_status, source_image_original_filename)` triple is computed identically; only the number of file reads changes. When the cache is empty, evicted, or the report/entity is missing, the helper returns `(None, None, None)` as before.  
  **Evidence from code:**  
  - `_enrich_position_traceability_from_report()` still:
    - Extracts `entity_uid` from `detected_summary_json`.  
    - Validates `entity_uid` shape and splits it into `job_id`.  
    - Loads `hybrid_report.json` once per job, iterates `entities`, and builds a normalized triple.  
  - `position_to_summary()` continues to:
    - Use enrichment only when `entity_uid` is present and at least one of the traceability fields is `None`.  
    - Fall back to summary JSON alone when enrichment returns `None` values.  

- **Finding C2 (Low)**  
  **Severity:** Low  
  **Explanation:** Cache eviction via `_maybe_evict_traceability_cache()` is coarse (full clear), but correctness is unaffected: at worst enrichment stops being available until the next file load, which is consistent with pre-cache behavior.  
  **Evidence from code:**  
  - `_maybe_evict_traceability_cache()` clears both `_TRACEABILITY_CACHE` and `_TRACEABILITY_REPORTS_LOADED` once either size threshold is exceeded.  
  - After eviction, `_enrich_position_traceability_from_report()` behaves as if the cache had never run: it either reloads a report (if not yet marked loaded) or returns `(None, None, None)` for jobs marked as loaded afterward.  

### 4.2 Safety

- **Finding S1 (Medium)**  
  **Severity:** Medium  
  **Explanation:** Without bounds, module-level caches can become a latent memory risk in long-lived processes. The corrective pass mitigates this with simple job/entity-count thresholds and an eviction helper, which is an appropriate level of safety for this system. Remaining risk is that thresholds are static and not configurable, but they are conservative and aligned with expected workloads.  
  **Evidence from code:**  
  - New globals:
    - `_MAX_TRACEABILITY_JOBS = 128`  
    - `_MAX_TRACEABILITY_ENTITIES = 4096`  
  - `_maybe_evict_traceability_cache()` logic:
    - If `len(_TRACEABILITY_REPORTS_LOADED) > _MAX_TRACEABILITY_JOBS` *or* `len(_TRACEABILITY_CACHE) > _MAX_TRACEABILITY_ENTITIES`, both structures are cleared.  
  - This prevents unbounded growth without increasing complexity or risk of partial invalidation bugs.

- **Finding S2 (Low)**  
  **Severity:** Low  
  **Explanation:** The code assumes `hybrid_report.json` is effectively immutable after being written, and this is now explicitly documented. If a report is rewritten while a process is running, the cache may serve stale data. For v3.1.2, this is acceptable because report regeneration is not a supported runtime operation and enrichment is best-effort.  
  **Evidence from code and docs:**  
  - `_enrich_position_traceability_from_report()` docstring explicitly states that it assumes `hybrid_report.json` is written once per job and treated as immutable.  
  - Stage 5 report v1.1 (Validation notes) documents that regenerated reports may not be re-read until a restart or eviction.  

### 4.3 Maintainability

- **Finding M1 (Low)**  
  **Severity:** Low  
  **Explanation:** The added structures and helpers are small and localized. Naming is clear (`_TRACEABILITY_CACHE`, `_TRACEABILITY_REPORTS_LOADED`, `_maybe_evict_traceability_cache`, `_reset_traceability_cache_for_tests`) and their purpose is documented. This keeps the optimization maintainable without introducing a general-purpose caching framework.  
  **Evidence from code:**  
  - Cache-related code is confined to a small section at the top of `shared.py` and to `_enrich_position_traceability_from_report`.  
  - Comments explain that the cache is best-effort, bounded, and assumes immutable reports.  

- **Finding M2 (Low)**  
  **Severity:** Low  
  **Explanation:** `_reset_traceability_cache_for_tests()` is a small, clearly named helper with a narrow purpose (test isolation). It does not affect production paths. This improves testability with negligible maintenance cost.  
  **Evidence from code:**  
  - The helper is defined at the bottom of `shared.py` with a docstring marking it as intended for tests or one-off scripts.  
  - No production routes or use cases call it.  

### 4.4 Scope control

- **Finding SC1 (Low)**  
  **Severity:** Low  
  **Explanation:** The corrective pass remained tightly scoped. All code changes are in `shared.py` and Stage 5 docs; no unrelated routes, repositories, or schemas were touched. The optimization was hardened but not expanded.  
  **Evidence from repository state:**  
  - Only `src/api/routes/v3/shared.py` and Stage 5 report files show diffs associated with this corrective pass.  
  - No changes to Pydantic schemas, SQL repositories, or frontend code.  

### 4.5 Documentation / report accuracy

- **Finding D1 (Low)**  
  **Severity:** Low  
  **Explanation:** `STAGE_5_V3.1.2_BACKEND_OPTIMIZATION_REPORT.md` now accurately describes Stage 5 as a **focused** optimization with a single concrete change (traceability cache) and explicitly states that other endpoints were reviewed and left unchanged. Cache behavior, bounds, and assumptions are documented.  
  **Evidence from docs:**  
  - Summary clearly calls out that the traceability cache is the only concrete optimization.  
  - Performance section describes the bounded cache, eviction behavior, and best-effort nature.  
  - Validation notes list assumptions and mention the test reset helper.  

- **Finding D2 (Low)**  
  **Severity:** Low  
  **Explanation:** `STAGE_5_V3.1.2_CORRECTIVE_PASS_REPORT.md` faithfully documents what the corrective pass did, concern by concern, and lists code/report changes and remaining deferred items. This improves auditability without adding noise.  
  **Evidence from docs:**  
  - The corrective report follows the requested structure (summary, concern-by-concern, code changes, lifecycle/assumptions, report accuracy, deferred items, validation).  
  - Descriptions match the actual diffs in `shared.py` and Stage 5 report v1.1.  

## 5. Positive notes

- The cache remains **internal and best-effort**: failure to enrich never affects correctness of core API behavior, only traceability metadata availability.
- **Bounds** on jobs/entities are small and hard-coded, striking a good balance between safety and simplicity for v3.1.2.
- The code is **well-documented**: docstrings and comments explain assumptions (immutable reports, per-process scope, graceful degradation).
- A tiny, clearly named test helper (`_reset_traceability_cache_for_tests`) improves test isolation without touching production flows.
- Stage 5 documentation was made **more honest and precise** about scope, avoiding overstating the amount of optimization work done.

## 6. Risks or gaps

- The cache eviction strategy is **all-or-nothing**: once thresholds are exceeded, the entire cache is cleared. This is acceptable but coarse; in extreme workloads, it may reduce cache hit rates. Severity is low because the fallback behavior is still correct and the thresholds are conservative.
- The assumption that `hybrid_report.json` is immutable is reasonable for this version, but not programmatically enforced. If future pipeline changes introduce report rewrites, this assumption may need to be revisited. For now, this is a documentation-level contract rather than a runtime invariant.
- The test reset helper is not yet used by any tests (as far as this audit can see); if future tests rely on the cache, they should explicitly call it for cross-test isolation.

## 7. Recommended follow-ups

All follow-ups are **optional** and low priority:

- If future workloads show many distinct jobs/entities in a single long-lived process, consider making `_MAX_TRACEABILITY_JOBS` / `_MAX_TRACEABILITY_ENTITIES` configurable via settings, keeping the same simple eviction semantics.
- When adding tests that exercise enrichment with real `hybrid_report.json` files, use `_reset_traceability_cache_for_tests()` in fixtures to ensure deterministic behavior across tests.
- If a future version introduces report rewrites or incremental updates, revisit the immutability assumption and decide whether enrichment should support refresh (e.g. by invalidating entries per job_id).

## 8. Final recommendation

The Stage 5 corrective pass for the traceability enrichment cache is **approved with observations**. The implementation is technically sound, bounded, and well-documented, and it remains proportionate to the problem it solves. No blocking issues were found; the noted risks are low and acceptable for v3.1.2, with clear paths for future adjustment if requirements evolve.

