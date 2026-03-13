# STAGE_1_FINDINGS_SUMMARY_V3.1.2.md

## A. Executive summary

- **Main technical debt:** Two job systems (legacy `jobs`/pallet_results/events + v3 `v3_jobs`/JobRepository), version-prefixed table (`v3_jobs`), and mixed v1/v3 API surface (frontend mostly v3, one v1 consumer). Backend and DB carry legacy job flow alongside the active v3 flow.
- **Biggest cleanup opportunities:** (1) Remove or clearly deprecate v1 routes and their consumers after tracing; (2) rename `v3_jobs` to a domain name; (3) consolidate frontend loading/empty/error components; (4) document and optionally isolate legacy DB/repos.
- **Biggest risks:** Deleting v1 endpoints or legacy tables without confirming every consumer; renaming tables without coordinated migration and repo updates; large structural reorg in a single change set.
- **Biggest easy wins:** Consolidate UI loading/empty/error components in frontend; add field-usage map for API responses and remove clearly unused fields; document architecture (v3 vs legacy) in one place.

---

## B. Backend findings summary

- **Routes:** All v3 routes are active and consumed by the frontend. v1 routes (jobs + entities) are active for at least one consumer (getJobEntities); other v1 endpoints (result, report, artifacts, entity evidence/review/audit) need consumer trace before removal.
- **Use cases / repos / schemas:** All are in use; no dead modules identified. Stage 8 repos (jobs, pallet_results, job_events) serve the legacy pipeline.
- **Recommendation:** Trace v1 consumers; then remove or deprecate unused v1 routes in Stage 2. Do not remove legacy job flow without product decision.

---

## C. Database findings summary

- **Active tables:** inventories, aisles, source_assets, positions, product_records, evidences, review_actions, v3_jobs.
- **Legacy tables:** jobs, pallet_results, job_events (used by legacy worker and v1 job creation/result).
- **Version-based name:** v3_jobs only. Candidate rename: e.g. `aisle_jobs` or `jobs` after legacy `jobs` is retired.
- **Recommendation:** Stage 3: migrate v3_jobs to target name; update SqlJobRepository. Do not drop legacy tables in v3.1.2 without explicit scope.

---

## D. Frontend findings summary

- **Active:** All four pages, features/results, api client (v3 + getJobEntities), hooks, shared components.
- **Legacy/unclear:** getJobEntities (v1) consumer to be confirmed; if none, remove client and types.
- **Structure:** Single feature module (results); inventory/aisle at page level. Opportunity to add features/inventories and features/aisles in Stage 7.
- **Recommendation:** Confirm v1 entity usage; consolidate loading/empty/error components in Stage 8.

---

## E. API contract findings summary

- **Alignment:** v3 responses match frontend consumption for inventories, aisles, positions, detail, metrics, execution log, assets. No major over-fetch or wrong shape.
- **Unused/reserved:** SourceAssetSummary.storage_path (reserved in types); position primary_evidence_id possibly redundant with has_evidence. Minor.
- **v1 entities:** Contract and consumer need confirmation before removal.
- **Recommendation:** Stage 5: build field-usage map; remove or document unused fields; optionally add lighter position summary DTO.

---

## F. Duplication findings summary

- **Backend:** Two job systems (legacy vs v3) are architectural duplication; consolidation is high impact and risky — document and defer. No other significant backend duplication.
- **Frontend:** Loading/empty/error components have 3–4 variants each; safe to consolidate. useInventories/useAisles/usePositions are acceptable duplication; optional generic hook is low priority.
- **Recommendation:** Stage 8: consolidate loading, empty, and error UI; leave job system consolidation for a later version.

---

## G. Structure findings summary

- **Backend:** Clear layers (api → application → domain + infrastructure). Legacy lives in database/ and jobs/; mixed responsibility in jobs/ (queue + worker + legacy store). Optional move of database/ to infrastructure/legacy/ in Stage 4.
- **Frontend:** Asymmetric features (only results); utils flat. Optional grouping of utils and addition of feature modules in Stage 7.
- **Recommendation:** Prefer documentation and small moves over big reorg in v3.1.2.

---

## H. Job lifecycle findings summary

- **Current states:** QUEUED, RUNNING, SUCCEEDED, FAILED (v3). No cancel_requested, canceled, or timed_out.
- **Gaps:** No cancellation checkpoints in pipeline; no timeout policy; frontend has no cancel action or new statuses.
- **Recommendation:** Stage 6: add new states and persist them; add cancel endpoint; check cancel (and timeout) before pipeline and ideally between stages; add timeout config; update frontend.

---

## I. Prioritized backlog for next stages

| # | Title | Severity | Type | Suggested stage | Rationale |
|---|--------|----------|------|------------------|------------|
| 1 | Trace all v1 endpoint consumers (result, report, artifacts, entity evidence/review/audit) | High | Unclear | Stage 2 | Required before removing any v1 route |
| 2 | Remove or deprecate v1 routes with no consumer | Medium | Legacy removal | Stage 2 | Reduce API surface after trace |
| 3 | Rename v3_jobs table to domain name (e.g. aisle_jobs) | Medium | Rename | Stage 3 | Align schema with domain; migration + SqlJobRepository update |
| 4 | Document dual job system (legacy vs v3) and retention policy | Low | Informational | Stage 2/3 | Clarify what can be removed later |
| 5 | Optional: move database/repository.py to infrastructure/legacy | Low | Reorg | Stage 4 | Isolate legacy persistence; update imports |
| 6 | Add job cancellation endpoint and cancel_requested/canceled/timed_out states | High | Job lifecycle | Stage 6 | Core v3.1.2 operational goal |
| 7 | Add cancellation checkpoints (before pipeline; between stages if feasible) | High | Job lifecycle | Stage 6 | Enable cooperative cancellation |
| 8 | Add timeout config and enforcement for v3 jobs | Medium | Job lifecycle | Stage 6 | Prevent stuck jobs |
| 9 | Consolidate frontend loading components (LoadingBlock, ResultsLoadingState, ResultDetailLoadingState) | Medium | Duplication | Stage 8 | High impact / easy win |
| 10 | Consolidate frontend empty and error state components | Medium | Duplication | Stage 8 | Reduce duplication |
| 11 | Build API response field-usage map and remove unused fields | Medium | Contract | Stage 5 | Cleaner payloads |
| 12 | Confirm getJobEntities consumer; remove if unused | Low | Legacy removal | Stage 2/8 | Clean frontend and optionally backend |
| 13 | Define target frontend feature structure (inventories, aisles, results) | Low | Reorg | Stage 7 | Guide reorg |
| 14 | Update tests and docs after any removal or rename | Medium | Validation | Stage 9 | Ensure stability and auditability |

---

**Stage mapping summary:**

- **Stage 2 — Backend legacy cleanup:** 1, 2, 4, 12 (trace v1, remove unused routes, document job systems, confirm getJobEntities).
- **Stage 3 — DB normalization:** 3 (rename v3_jobs).
- **Stage 4 — Backend reorg:** 5 (optional legacy move); document structure.
- **Stage 5 — Backend optimization:** 11 (field-usage map, remove unused fields).
- **Stage 6 — Job cancellation:** 6, 7, 8 (endpoint, checkpoints, timeout).
- **Stage 7 — Frontend reorg:** 13 (target structure; optional feature modules).
- **Stage 8 — Frontend optimization:** 9, 10 (consolidate loading/empty/error); 12 if frontend-only.
- **Stage 9 — Validation and closure:** 14 (tests, docs).

All audit artifacts (AUDIT_BACKEND, AUDIT_DATABASE, AUDIT_FRONTEND, AUDIT_API_CONTRACTS, AUDIT_DUPLICATION, AUDIT_STRUCTURE, AUDIT_JOB_LIFECYCLE) are the source of truth for these findings and recommendations.
