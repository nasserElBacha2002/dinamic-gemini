# STAGE_5_V3.1.2_CORRECTIVE_PASS_REPORT.md

## 1. Summary

This corrective pass reviews and hardens the **Stage 5 backend optimization** for Dinamic Inventory v3.1.2. Stage 5 introduced a traceability enrichment cache in `src/api/routes/v3/shared.py` to avoid repeatedly reading the same `hybrid_report.json` file for multiple positions from the same job; no response contracts were changed.

The corrective goals were to ensure that this optimization has a safe lifecycle, clear assumptions (especially around report immutability), minimal test/process contamination risk, and accurate documentation. The cache remains in place, with small adjustments: a simple bounding strategy, clearer comments and assumptions, and an internal reset helper for tests. The Stage 5 report was updated to more precisely describe the scope and the cache behavior.

---

## 2. Concern-by-concern assessment

### Concern 1 — Global in-process cache lifecycle

**Assessment:** The cache uses module-level globals:
- `_TRACEABILITY_CACHE: Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]]` keyed by `entity_uid`.
- `_TRACEABILITY_REPORTS_LOADED: Set[str]` keyed by `job_id`.

Without bounding, these structures could grow unbounded in a very long-lived process that touches many distinct jobs/entities, even though typical workloads likely only exercise a modest set.

**Evidence:**
- The cache lives in `shared.py` and is used only by `_enrich_position_traceability_from_report`, which is called via `position_to_summary` from positions list/detail endpoints.
- There was no eviction logic; entries were only added.

**Action taken:**
- Introduced **small, best-effort bounds** and an eviction helper:
  - `_MAX_TRACEABILITY_JOBS = 128`
  - `_MAX_TRACEABILITY_ENTITIES = 4096`
  - `_maybe_evict_traceability_cache()` clears both `_TRACEABILITY_CACHE` and `_TRACEABILITY_REPORTS_LOADED` when either threshold is exceeded.
- This keeps the cache **bounded per process**, avoiding unbounded growth while preserving the common-case optimization (few jobs per process).
- Kept the cache as simple module-level state, in line with the existing shared helper style; no new caching subsystem or external dependency was introduced.

### Concern 2 — Staleness assumptions

**Assessment:** The optimization assumes that once a job’s `hybrid_report.json` has been read, its contents do not change for the life of the backend process. If reports were re-generated while the process is running, `_TRACEABILITY_REPORTS_LOADED` could prevent re-reading newer contents.

**Evidence:**
- The report is produced by the pipeline at the end of a job run. In the existing architecture, reports are treated as **outputs**, not as mutable runtime state.
- There is no code path that rewrites `hybrid_report.json` after a pipeline completion; subsequent updates would be out-of-band operations.
- `_enrich_position_traceability_from_report` is a best-effort enrichment step; failing to refresh in-process when a report is manually edited is acceptable in v3.1.2.

**Action taken:**
- Explicitly documented the **immutability assumption** in the `_enrich_position_traceability_from_report` docstring and in the Stage 5 report:
  - Assumes `hybrid_report.json` is written once per job and treated as immutable for the life of the backend process.
  - If a report is regenerated while a process is running, enrichment may use the older contents until the process restarts or until the cache is evicted.
- Kept the behavior as-is (no periodic refresh), since report mutation during runtime is not a supported pattern in v3.1.2 and the cache is best-effort.

### Concern 3 — Test/process contamination risk

**Assessment:** Module-level cache state could leak between tests in the same process or between unrelated requests in a long-lived process. For production this is acceptable (cache is per-process), but tests may want isolation.

**Evidence:**
- `_TRACEABILITY_CACHE` and `_TRACEABILITY_REPORTS_LOADED` were only created and mutated; there was no way to reset them without reloading the module.
- Tests for result mappers mostly operate on mocked data and do not currently rely on actual `hybrid_report.json` loading, but future tests might.

**Action taken:**
- Added `_reset_traceability_cache_for_tests()` in `shared.py`:
  - Clears both `_TRACEABILITY_CACHE` and `_TRACEABILITY_REPORTS_LOADED`.
  - Documented as intended for tests or one-off scripts and **not used by production code paths**.
- This allows tests to call the helper if they need strict isolation across cases without affecting runtime behavior.

### Concern 4 — Accuracy of Stage 5 scope in the report

**Assessment:** The original Stage 5 report described a “backend optimization” stage; in practice, Stage 5 implemented **one targeted optimization** (traceability enrichment cache) and validated that other v3 endpoints were already acceptable.

**Evidence:**
- Code diffs from Stage 5 show only changes in `shared.py` around `_enrich_position_traceability_from_report` and no contract/query changes elsewhere.
- The report already described other endpoints as “acceptable as-is”, but the summary did not explicitly say that only a single optimization was implemented.

**Action taken:**
- Updated the Stage 5 report summary to explicitly state that Stage 5 is a **focused backend optimization pass**, and that the **single concrete optimization** is the traceability enrichment cache, with other routes left unchanged after explicit review.
- Clarified that broader contract/query changes were **intentionally deferred** to keep v3.1.2 low-risk.

### Concern 5 — Documentation of non-optimized areas

**Assessment:** The report claimed that other endpoints were acceptable as-is; this needed clear, concise justification.

**Evidence:**
- Inventories, aisles, assets, positions, reviews routes and corresponding frontend usage were inspected in Stage 5.
- Aisle status and execution log use batched queries and thin payloads.
- Position list/detail contracts match frontend result mappers, and SQL repositories already avoid N+1 patterns.

**Action taken:**
- Left the optimization matrix and query/performance sections structurally the same but clarified:
  - Why each endpoint was left unchanged (e.g., batched job lookups, thin responses, explicit summary/detail split).
  - That **no schemas were changed** and which fields were kept vs. deferred, with reference to Stage 1 findings.
- Added more explicit wording that non-optimized areas were *reviewed and deliberately left as-is*, not ignored.

### Concern 6 — Naming and encapsulation quality

**Assessment:** Cache naming was already fairly clear, but internal behavior and assumptions could benefit from more explicit comments and a small helper for eviction.

**Evidence:**
- `_TRACEABILITY_CACHE` and `_TRACEABILITY_REPORTS_LOADED` names communicated their purpose, but there was no mention of bounds or immutability assumptions.
- `_enrich_position_traceability_from_report` lacked a docstring describing assumptions and failure behavior.

**Action taken:**
- Kept existing names, but:
  - Added `_MAX_TRACEABILITY_JOBS`, `_MAX_TRACEABILITY_ENTITIES`, and `_maybe_evict_traceability_cache()` for bounded behavior.
  - Added a docstring to `_enrich_position_traceability_from_report` describing assumptions (immutable reports, best-effort enrichment, graceful failure) and its internal-optimization nature.
- The function body remains readable and localized; no additional abstraction layer was introduced.

---

## 3. Code changes applied

**File:** `src/api/routes/v3/shared.py`

- **Cache bounding and typing:**
  - Extended imports: `from typing import Dict, List, Optional, Set, Tuple`.
  - Documented cache intent and assumptions above the globals.
  - Introduced:
    - `_TRACEABILITY_REPORTS_LOADED: Set[str] = set()` (explicit type).
    - `_MAX_TRACEABILITY_JOBS = 128`
    - `_MAX_TRACEABILITY_ENTITIES = 4096`
    - `_maybe_evict_traceability_cache()` to clear cache/set when either bound is exceeded.
- **Enrichment helper documentation and eviction call:**
  - Added a docstring to `_enrich_position_traceability_from_report` outlining:
    - Assumption of immutable `hybrid_report.json` per job.
    - Best-effort behavior and graceful degradation.
  - After populating `_TRACEABILITY_CACHE` and marking the job as loaded, now calls `_maybe_evict_traceability_cache()`.
- **Test reset hook:**
  - Added `_reset_traceability_cache_for_tests()` which clears `_TRACEABILITY_CACHE` and `_TRACEABILITY_REPORTS_LOADED`, documented as test/support-only.

**File:** `docs/3.1.2/STAGE_5_V3.1.2_BACKEND_OPTIMIZATION_REPORT.md`

- **Summary:**
  - Clarified that Stage 5 is a **focused backend optimization pass** and that the **single concrete optimization** is the traceability cache; other endpoints were explicitly reviewed and left unchanged.
- **Performance section:**
  - Described the cache as **bounded**, mentioning `_MAX_TRACEABILITY_JOBS`, `_MAX_TRACEABILITY_ENTITIES`, and `_maybe_evict_traceability_cache()`.
  - Updated impact notes to include bounded behavior.
- **Validation notes:**
  - Expanded traceability cache notes to cover:
    - Immutable report assumption.
    - Behavior when reports are regenerated mid-process.
    - The existence and purpose of `_reset_traceability_cache_for_tests()`.
- **Version bump:**
  - `Document version` updated from `1.0` to `1.1` with a brief corrective-pass note.

---

## 4. Cache lifecycle and assumptions

- **Lifecycle:**
  - Cache lives for the life of the backend process, shared across requests within that process.
  - Bounded via `_MAX_TRACEABILITY_JOBS` and `_MAX_TRACEABILITY_ENTITIES`. When limits are exceeded, both cache and job set are cleared.
  - Behavior degrades gracefully to “no enrichment” rather than failing when the cache is empty or evicted.

- **Staleness assumptions:**
  - `hybrid_report.json` is assumed to be **written once per job by the pipeline** and treated as immutable while the backend process is running.
  - If a report is manually regenerated while a process is live, the cache may serve the older contents until the process restarts or the cache is evicted.
  - This is acceptable in v3.1.2 because report regeneration at runtime is not a supported workflow; enrichment is best-effort.

- **Reset / test hooks:**
  - `_reset_traceability_cache_for_tests()` clears both internal structures and is intended for tests or tooling that need strict isolation.
  - Production code paths do not call this function.

- **Not handled (intentionally):**
  - No per-entity expiration or per-job TTL; eviction is coarse (full clear when bounds exceeded) to keep implementation simple.
  - No persistence across processes; cache is per-process only.

---

## 5. Report accuracy adjustments

- The Stage 5 report now:
  - Emphasizes that the main optimization is the traceability enrichment cache and that other endpoints were **reviewed and consciously left unchanged**.
  - Clearly documents cache behavior, bounds, and assumptions.
  - States that no contracts or queries were modified, and lists which fields were kept vs. deferred along with reasons.

No structural changes to the Stage 5 plan were made; the report is now more explicit and honest about the narrow but high-value scope of the work.

---

## 6. Remaining deferred items

- **Field and contract slimming:** Still deferred; any removal or reshaping of v3 DTOs is expected to happen in a future, versioned contract change.
- **More granular caching policies:** No per-entity or per-job TTLs; such policies would add complexity and are not justified for v3.1.2.
- **Asset file endpoint query optimization:** Potential repository-level optimization (get-by-id) remains deferred as in the original Stage 5 report.

---

## 7. Validation notes

- **API behavior:**
  - No changes to Pydantic schemas or FastAPI `response_model` declarations; all v3 routes continue to return the same shapes.
  - Frontend types and mappers (`features/results`, `usePositions`, API client) were not changed and remain aligned.
- **Traceability enrichment behavior:**
  - For a given `entity_uid`, enrichment still returns the same values as before when the report is present; only the number of filesystem reads has changed.
  - When the cache is cleared or a report is missing/invalid, behavior degrades to “no enrichment” (fields remain `None`), same as pre-optimization fallback.
- **Static checks:**
  - Linter checks over updated backend and report files show no new issues.

---

**Document version:** 1.0  
**Stage:** 5 — Backend optimization corrective pass  
**Date:** 2025-03-06
