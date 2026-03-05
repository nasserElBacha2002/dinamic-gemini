# Branch Review — Stage 2.1 (A + optional B + D + E)

**Branch:** `release-2.1` vs `main`  
**Scope:** Stage 2.1 end-to-end (v2.1 entities, reporting, evidence, assisted counting API).  
**Source of truth:** `docs/PLAN_V2.1_IMPLEMENTATION.fixed.md`.

---

## 1) Executive Summary

- **Is Stage 2.1 shippable?** **Yes, with fixes.** Core flow (2.1.A, 2.1.D, 2.1.E) is implemented and aligned with the plan. A few must-fix and high-priority items should be addressed before merge.
- **Top 3 risks:**
  1. **Path safety:** `job_id` and `entity_uid` are used in paths without strict validation; a malicious `job_id` (e.g. `..` or `foo/../bar`) could lead to path traversal in FS-backed job/review/evidence resolution.
  2. **Summary recomputation vs entity_type:** For resolved report, `summary.empty_pallets` counts only `entity_type == EMPTY_PALLET`. A PALLET marked EMPTY via review stays in `pallets` and is not in `empty_pallets`; acceptable per plan but worth documenting for operators.
  3. **Uncommitted Stage 2.1.E/D assets:** New modules `src/review/`, `src/evidence/`, `src/api/routes/entities.py`, and tests `test_stage_2_1_e.py` / `test_evidence.py` appear untracked in the diff; ensure they are committed so the branch is complete and CI can run.

---

## 2) Requirements Compliance Matrix

| Substage | Status | Evidence | Follow-ups |
|----------|--------|----------|------------|
| **2.1.A** | ✅ Met | `entity_order.py`, `pallet_id.py`, `count_status.py`, `quality_score.py`; `global_analysis_schema.py` (v21); `global_analysis_parser.py` (parse_entities, entity_uid, original_index); `hybrid_report.py` (summary + counted_manual); pipeline: parse → sort → resolve_pallet_id → assign_count_status → quality_score; no visual fallback in hybrid path. | Document quality_score deviation (has_boxes vs local barcode) when 2.1.B absent. |
| **2.1.B** | ❌ Not present | No `src/barcode/`; no BARCODE_* config. | Optional per plan; no change required. Add in follow-up if needed. |
| **2.1.D** | ✅ Met | `src/evidence/evidence_pack.py` (localized/UNLOCALIZED, bbox); `paths.py` (slug); `scoring.py`; config EVIDENCE_*; pipeline calls `generate_evidence_pack`; `evidence_index.json` with entities[].evidence, evidence_localization. | None. |
| **2.1.E** | ✅ Met | `src/review/review_store.py`, `review_merge.py`; `src/api/routes/entities.py` (GET entities, evidence, POST review, GET audit); GET `/{job_id}/report?resolved=true` in jobs; entity_uid resolution and 400 when pallet_id duplicated. | Harden job_id/entity_uid in paths (see Critical). |

---

## 3) Critical Issues (must-fix before merge)

### 3.1 Path traversal via `job_id` (and `entity_uid` in evidence paths)

- **Where:** `src/jobs/job_store.py` uses `_job_dir(base_path, job_id) => base_path / job_id`. If `job_id` is `".."` or `"x/../etc"`, resolution can escape `output_dir`. Same risk in API routes that pass `job_id` into `_resolve_report_and_run_dir` and thus into paths read from the job record (report path comes from DB/FS record; the record is stored under `base_path / job_id`, so a malicious job_id can still cause writes/reads under a wrong dir if job.json were ever crafted).
- **Impact:** Information disclosure or overwrite if an attacker can control `job_id` (e.g. via API path parameter).
- **Fix:** Validate `job_id` (and path param for `entity_uid`) before use. Allow only safe tokens, e.g. `re.match(r"^[a-zA-Z0-9_-]+$", job_id)` and reject otherwise with 400. In `job_store`, sanitize or reject `job_id` in `create_job`, `get_job`, `update_job`, `list_artifacts`. In `entities.py`, validate `entity_uid` path param (or accept same pattern as entity_uid format `job_xxx_E1`). Apply the same rule wherever path segments are derived from user input.

---

## 4) High / Medium / Low Issues

### HIGH

- **entity_quality_score formula vs plan:** Plan: “+0.1 if position_barcode was set or confirmed by local hardening (2.1.B)”. Code: `quality_score.py` uses “+0.1 if entity_type == PALLET and has_boxes”. **Risky deviation** when 2.1.B is added later (formula will need to include local-barcode flag). For current branch without 2.1.B, acceptable; add a short comment in `quality_score.py` that +0.1 is has_boxes for now and will be replaced by “local barcode” when 2.1.B is implemented.
- **GET report vs plan path:** Plan says `GET /api/v1/jobs/{job_id}/report?resolved=true`. Implemented as `GET /api/v1/inventory/jobs/{job_id}/report`. **Acceptable** (same resource, different prefix); ensure API docs or OpenAPI reflect the actual path.
- **Resolved report summary and EMPTY:** When an entity is marked EMPTY via review, it remains `entity_type PALLET`, so `summary.empty_pallets` does not increase. Only `count_status` and `final_quantity` change. Per plan, `empty_pallets` is “entity_type == EMPTY_PALLET”, so behavior is correct; document in API or report schema that “empty_pallets” is by type, not by review status.

### MED

- **Review store `load_reviews` return shape:** `review_merge.merge_resolved_report` expects `reviews` as dict keyed by `entity_uid` with `{ entity_uid, events }`. `review_store.load_reviews` returns that shape. Consistency is correct; add a one-line comment in `review_merge` or store module documenting the contract (e.g. “reviews: entity_uid -> { entity_uid, events: [{ after, ... }] }”).
- **Idempotency of POST review:** Plan mentions “idempotent where specified”. Current implementation appends an event every time; multiple identical POSTs create multiple events. If the plan requires idempotency for “same action + same entity + same payload”, consider deduplication or last-write-wins semantics and document; otherwise document that each POST creates a new audit event (current behavior).
- **Evidence index missing:** `GET .../entities/{entity_uid}/evidence` returns 404 when `evidence_index.json` is absent (e.g. job from before 2.1.D or failed evidence step). Behavior is correct; ensure client docs or error message indicate that evidence is only available for runs that produced evidence (v2.1.D).

### LOW

- **Duplicate `_resolve_report_and_run_dir` usage in entities:** `entities.py` delegates to `jobs._resolve_report_and_run_dir` to avoid circular import; that’s fine. Consider extracting a shared helper in a small module (e.g. `src.api.deps` or `src.jobs.paths`) used by both jobs and entities to avoid coupling routes to each other.
- **Magic action names:** `ACTIONS = ("SET_COUNT", "MARK_EMPTY", "MARK_INVALID")` in `review_merge.py`; no config. Plan allows MVP without config for these; add a short comment that they can be moved to config later if needed.
- **Logging:** Review store and merge do not log save/merge events; add minimal debug log on save_review and on merge (e.g. “merged N review overrides”) for operational visibility.

---

## 5) Determinism & Data Integrity Audit

| Check | Result | Notes |
|-------|--------|------|
| **Deterministic ordering before generated IDs** | ✅ | `sort_entities_deterministically(entities)` in pipeline before `resolve_pallet_id(entities)`; key `(model_entity_id, original_index)`. |
| **Duplicate position_barcode conflict** | ✅ | `resolve_pallet_id` sets `conflict_flag`, `conflict_reason = "DUPLICATE_POSITION_BARCODE"` for duplicate barcode indices; `assign_count_status` keeps NEEDS_REVIEW when `conflict_flag`; no suffix on pallet_id. |
| **No visual fallback for v2.1** | ✅ | Hybrid path does not call legacy visual fallback; single Gemini call → parse → sort → resolve → assign status → quality → evidence → report. |
| **Evidence pack determinism** | ✅ | Same frames + same entities imply same sharpness/dedupe and same bbox crops; no randomness in evidence_pack. |
| **Review merge does not mutate original report** | ✅ | `merge_resolved_report` does `report = dict(report)` and `entities = list(...)`; only the copy is mutated; file is not written. |
| **Summary recomputation** | ✅ | `_summary_from_entity_dicts` in `review_merge.py` recomputes all summary fields from merged entities; base report `_build_summary_from_entities` includes `counted_manual` (0 in base). |

---

## 6) API Contract Review (2.1.E)

- **Endpoints:**
  - `GET /api/v1/inventory/jobs/{job_id}/entities?status=&entity_type=` — list entities; filters optional.
  - `GET /api/v1/inventory/jobs/{job_id}/entities/{entity_uid}/evidence` — evidence paths from evidence_index.
  - `POST /api/v1/inventory/jobs/{job_id}/entities/{entity_uid}/review` — body: action, final_quantity (for SET_COUNT), actor, notes.
  - `GET /api/v1/inventory/jobs/{job_id}/entities/{entity_uid}/audit` — list of review events.
  - `GET /api/v1/inventory/jobs/{job_id}/report?resolved=true` — resolved report (merge + summary recompute).
- **entity_uid:** Used in path and in responses; when `pallet_id` is duplicated, 400 “Multiple entities share this pallet_id; use entity_uid”. Resolution: by entity_uid first, then by unique pallet_id.
- **Error handling:** 404 for job not found, report not found, entity not found, evidence index not found; 409 for job not succeeded; 422 for invalid action or missing final_quantity for SET_COUNT; 400 for duplicate pallet_id without entity_uid.
- **Idempotency:** POST review is not idempotent (each call appends an event); document or adjust per product requirement.

---

## 7) Test Coverage Review

- **Covered:** Schema v21 validation; parse_entities (entity_uid, original_index); sort order; resolve_pallet_id (duplicate barcode → conflict); assign_count_status branches; entity_quality_score; pipeline integration (test_stage_2_1_a); review store load/save/audit; merge and summary recomputation; API entities list (with filter), evidence, POST review (success + 422 + 404), audit, report?resolved=true (test_stage_2_1_e); evidence pack structure and localization (test_evidence).
- **Missing / suggested:**
  - **test_review_merge_empty_reviews:** `merge_resolved_report(report, {})` returns report with unchanged entities and same summary (no crash, no mutation of input).
  - **test_entity_resolve_by_pallet_id_unique:** GET evidence with unique pallet_id (not entity_uid) returns 200 and same evidence ref.
  - **test_report_resolved_no_reviews_file:** GET report?resolved=true when run_dir has no reviews.json returns report identical to resolved=false (merge with empty reviews).
  - **test_job_id_invalid_chars:** GET /jobs/../other or /jobs/foo/bar returns 404 or 400 (once job_id validation is added).
  - **Determinism:** Two runs of pipeline with same Gemini mock payload produce same entity order and same PALLET_001, PALLET_002 (test_stage_2_1_a likely covers; add explicit assertion on ordered list of pallet_ids if not already).

---

## 8) Security / Operational Considerations

- **Path traversal / unsafe filenames:** See Critical (job_id/entity_uid validation). Evidence paths use `slug(entity_uid)` in `paths.py`, which restricts to alphanumeric, underscore, hyphen — good.
- **Storage growth:** Reviews are one JSON file per job; no cap. Consider a follow-up: limit events per entity or size of reviews.json, or document retention.
- **Logging of sensitive data:** No logging of barcode/label text in the reviewed code; keep audit events (before/after, actor) in reviews.json only and avoid logging full payloads.
- **Backward compatibility:** Report v2.1 has report_version and mode hybrid_v2.1; worker and DB push map entities to pallet_results for v2.1; GET result and GET report return same shape; legacy mode unchanged. Resolved report is additive (query param).

---

## 9) Suggested Follow-up PRs

- **Path safety:** Centralize job_id and entity_uid validation (regex or allowlist) and use in job_store and API.
- **Config:** Move evidence/review constants (e.g. ACTIONS, REVIEWS_FILENAME) to config or constants module if they should be tunable.
- **Docs:** One-page “Stage 2.1 API” (entities, evidence, review, resolved report) and update OpenAPI tags/descriptions.
- **2.1.B:** If barcode hardening is added, add +0.1 for “local barcode” in quality_score and keep or replace has_boxes term; add BARCODE_* config and tests.

---

## Merge Recommendation

**Approve with fixes**

- **Must do before merge:** Add validation for `job_id` (and path param `entity_uid` where used in paths) to prevent path traversal (Critical 3.1).
- **Should do:** Document entity_quality_score deviation (has_boxes vs local barcode); document that POST review is not idempotent; ensure all new Stage 2.1.E/D files and tests are committed and green.
- **Can do in follow-up:** MED/LOW items (comments, optional idempotency, shared resolver module, extra tests).

After addressing the critical path-safety validation, the branch is suitable to merge for Stage 2.1 (A + D + E) with the above follow-ups tracked.
