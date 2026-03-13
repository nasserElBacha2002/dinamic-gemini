# AUDIT_DUPLICATION_V3.1.2.md

## 1. Summary

This document reports the duplication audit for Dinamic Inventory v3.1.2 across backend and frontend. It identifies repeated patterns and classifies them as safe to consolidate, requiring design decision, acceptable, or unclear.

## 2. Scope

- **Included:** Backend (validation, mapping, response assembly, repository access, error handling, job status); frontend (components, hooks, transforms, loading/error handling, API consumption, types).
- **Excluded:** Pipeline/CV logic not tied to API or UI.

## 3. Findings

### 3.1 Backend duplication

**Validation logic:**

- `validate_job_id`, `validate_entity_uid`, `validate_relative_path` in `src/utils/validation.py` — single place; used by routes and pipeline. **No duplication.**
- Route-level checks (e.g. aisle belongs to inventory) repeated in multiple route handlers; delegated to use cases where use cases exist. **Acceptable** (thin routes).

**Response building:**

- `_asset_to_response`, `_position_to_summary`, etc. in `inventories_v3.py` — helpers per entity type; no repeated response shape built in multiple files. **Acceptable.**
- Entities router builds responses from report JSON directly; v3 routes use use-case output + mappers. **Different sources** (report file vs domain); not same-concept duplication.

**Mapping logic:**

- `v3_report_mapper.map_hybrid_report_to_domain` — single mapper for report → domain. **No duplication.**
- Position summary enrichment (e.g. loading source_image_id from report when missing) in `inventories_v3.py` — logic in one place. **Acceptable.**

**Repository/query access:**

- Each repository has one SQL impl and one memory impl; no duplicated query logic across repos. **No duplication.**

**Job status handling:**

- Two systems: (1) legacy `JobStatus` in `jobs/models.py` + job_store; (2) domain `JobStatus` in `domain/jobs/entities.py` + JobRepository. **Architectural duplication** (two job models); consolidation would require merging job flows. **Requires design decision.**

**Error handling:**

- `_review_exception_to_http` in inventories_v3 maps app exceptions to HTTP; other routes raise HTTPException directly. **Acceptable** (review flow has many exception types).
- ApiError / messageFromErrorDetail on frontend; backend uses HTTPException(detail=...). **Aligned**; no duplication across layers.

**Helper functions:**

- `_resolve_report_and_run_dir` in jobs.py; entities.py imports it from jobs. **Single definition.** Path resolution for execution log in inventories_v3 uses load_settings + RUN_ID. **Acceptable** (different contexts).

### 3.2 Frontend duplication

**Components:**

- Loading states: LoadingBlock, ResultDetailLoadingState, ResultsLoadingState — similar purpose (spinner/block). **Safe to consolidate** into a single loading component with optional variant (e.g. full page vs inline).
- Empty states: ResultsEmptyState, ResultDetailEmptyState, ResultsFilteredEmptyState, EmptyState (ui). **Overlap** in message and layout; could be one component with props. **Safe to consolidate** (low risk).
- Error states: ErrorAlert, ResultDetailErrorState, ResultsErrorState — similar pattern. **Safe to consolidate.**

**Hooks:**

- useInventories, useAisles, usePositions — same pattern (queryKey + queryFn from client). **Acceptable duplication** (different resources); could be abstracted to a generic useQuery wrapper later. **Low impact / easy** if desired.

**Transforms/selectors:**

- positionToResult, detectedSummary mappers in features/results; selectors (resultsFilters, resultsKpi). **Single place per concept.** **No duplication.**

**Loading/error handling:**

- Multiple components set loading/error locally; React Query provides isPending/isError. Pattern repeated but not copy-paste. **Acceptable**; could standardize with a small hook (e.g. useQueryState) that returns { loading, error, data }. **Low impact.**

**Repeated API consumption:**

- Each hook calls one client function; no duplicate fetch logic. **No duplication.**

**Types:**

- API types in api/types/; results types in features/results/types.ts. ResultSummary/ResultDetail extend or map from API types; no duplicate definition of the same contract. **No duplication.**

### 3.3 Cross-layer

- Backend JobSummary vs frontend JobSummary: same intent (id, status, created_at, updated_at, error_message). **Acceptable** (contract alignment; not code duplication).
- Position status, aisle status, traceability status: backend and frontend share same literal sets. **Aligned**; single source of truth per layer.

## 4. Classification and priority


| Duplication                                   | Classification                    | Priority                  |
| --------------------------------------------- | --------------------------------- | ------------------------- |
| Two job systems (legacy vs v3)                | Requires design decision          | High impact / risky       |
| Loading components (3+ variants)              | Safe to consolidate               | High impact / easy win    |
| Empty state components (4)                    | Safe to consolidate               | Medium / easy             |
| Error state components (3)                    | Safe to consolidate               | Medium / easy             |
| useInventories/useAisles/usePositions pattern | Acceptable; optional generic hook | Low impact / easy         |
| Review exception mapping                      | Acceptable                        | Low / not worth in v3.1.2 |


## 5. Risks

- Consolidating loading/empty/error components: ensure all current usages (e.g. different copy or layout) are preserved via props.
- Merging two job systems: high risk; should be a dedicated design and migration, not part of routine duplication cleanup.

## 6. Recommendations

- Backend: Do not merge legacy and v3 job systems in v3.1.2; document the split and plan for a future consolidation if product retires legacy flow.
- Frontend: In Stage 8, consolidate loading, empty, and error UI into shared components with variants; then refactor pages/features to use them.

## 7. Candidate next-stage actions

- **Stage 5 (Backend):** No high-value duplication removal beyond eventual job-flow consolidation (out of scope for v3.1.2).
- **Stage 8 (Frontend):** Consolidate LoadingBlock/ResultsLoadingState/ResultDetailLoadingState; consolidate empty states; consolidate error states. Add generic useQueryState or keep current hooks as-is.

