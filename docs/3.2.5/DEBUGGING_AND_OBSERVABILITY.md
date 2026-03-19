# v3 Debugging and Observability (3.2.5 Phase 4 + Phase 7)

**Release**: 3.2.5 — Phase 4 (Observability and Debugging); Phase 7 (Observability hardening)  
**Purpose**: Make v3 runs reconstructable and diagnosable without building an enterprise observability platform. This document inventories current traceability, defines minimum metadata and stage boundaries, and records error-context guarantees.

---

## 1. Observability inventory

### 1.5 Canonical pipeline stage names (Phase 7)

The following stage names are the **canonical vocabulary** used in:

- **execution_log** (JSONL events: `stage` field)
- **last_stage_error.txt** (first token: "StageName: message")
- Stage-level investigation and regression isolation

| Stage name | Description |
|------------|-------------|
| **InputPreparationStage** | Validate input, prepare run dir, normalize photos. |
| **FrameAcquisitionStage** | Obtain frames from FrameSource and load into memory. |
| **AnalysisStage** | Call analysis provider (e.g. Gemini); raw output and parse. |
| **EntityResolutionStage** | Parse analysis payload, entity validation/transformation. |
| **EvidenceStage** | Generate evidence pack (overview + crops). |
| **ReportingStage** | Assemble report payload and write hybrid_report.json. |
| **Persist** | Post-pipeline: write positions/product_records/evidence to DB. Not a pipeline stage; used in error_message when persist fails (e.g. "Persist: ..."). |

When correlating a failure with a stage, match `error_message` or execution_log `stage` to one of these names.

### 1.1 Current sources of truth

| Source | Location | Persisted? | Consumed by API/Frontend? | Notes |
|--------|----------|------------|---------------------------|------|
| **Job metadata** | `inventory_jobs` (DB) via `JobRepository` | Yes | Yes | status, updated_at, error_message, result_json (report_path, visual_reference_context). Exposed in list/status/cancel and execution-log validation. |
| **Aisle lifecycle** | `aisles` (DB) | Yes | Yes | status, error_code, error_message, retryable. Exposed in list/status. |
| **Execution log** | `{output_dir}/{job_id}/run/execution_log.jsonl` | Filesystem | Yes (GET execution-log) | JSONL events: ts, stage, level, message, optional payload. Best-effort; `events: []` when missing/invalid/unreadable — does not necessarily mean no stages ran (see `ARTIFACT_HISTORICAL_READ_BOUNDARY.md` §5). |
| **Last stage error** | `{output_dir}/{job_id}/run/last_stage_error.txt` | Filesystem | No (internal) | Single line "StageName: message". Read by executor on pipeline exit_code != 0 and appended to job.error_message. |
| **Hybrid report** | `{output_dir}/{job_id}/run/hybrid_report.json` | Filesystem | Indirect | Entities with source_image_id, traceability_status, quantities, etc. Used by persist; also by shared traceability enrichment for list/detail. |
| **Input manifest** | `{output_dir}/{job_id}/input_manifest.json` | Filesystem | No | Photos list (image_id, original_filename, stored_filename). Used for HEIC/normalized path resolution and preview. |
| **Positions / products** | DB (positions, product_records) | Yes | Yes | detected_summary_json, corrected_summary_json; qty_source, qty_inference_reason, qty_parse_status (product_records). Exposed in positions list/detail. |
| **Evidences / review actions** | DB | Yes | Yes | Evidences and review history for positions. |
| **Run metadata (in-memory)** | Propagated to `job.result_json` | Yes (in result_json) | Internal only | visual_reference_context; **provider** (Phase 7); **prompt_key** when attributable (Phase 7). Stored on success; **result_json is an internal persisted metadata container, not a public API contract** — not exposed as a dedicated API field. |

### 1.2 Current gaps (updated Phase 7)

- **Provider attribution**: **Addressed in Phase 7.** Provider is now persisted in `job.result_json` on successful runs, so a run can be attributed to a model from DB without requiring execution_log.
- **Prompt attribution**: When `hybrid_prompt` is set and cleanly attributable to the run, **prompt_key** is persisted in `job.result_json`. Otherwise prompt attribution remains config/code derived; per-job prompt_key is deferred when not attributable.
- **Stage at failure**: When the pipeline fails, `last_stage_error.txt` holds "StageName: message" and the executor surfaces it in job.error_message. When **persist** fails (after pipeline succeeds), the exception was previously surfaced without a "Persist:" prefix; Phase 4 adds that prefix so the failing stage is explicit.
- **Per-entity parse/merge provenance**: qty_source, qty_inference_reason, qty_parse_status are persisted on ProductRecord and exposed in position summary (qtySource, qtyInferenceReason; qtyResolved). detected_summary_json carries a copy of qty metadata. Merge/consolidation is reflected by qty_source=consolidated and by aggregated_from_ids in detected_summary_json where applicable. No separate "merge reason" field exists.
- **Artifact references**: result_json.report_path points to hybrid_report.json. Evidence and asset paths are in DB; no single "artifacts that support this result" list is exposed.

### 1.3 Persisted vs logged-only vs transient (Phase 7)

- **Persisted (DB / result_json)**: Job (status, error_message, result_json including **provider**, and when attributable **prompt_key**; report_path; visual_reference_context). Aisle (status, error_*). Positions, product_records, evidences, review_actions. **Provider in result_json** = persisted; allows run attribution from DB without execution_log.
- **Logged-only / best-effort artifact**: **Provider in execution_log payload** = logged-only (same value may also be in result_json after Phase 7). execution_log and hybrid_report are **best-effort artifact-based**; retention is filesystem-based. last_stage_error is file-backed, then copied into job.error_message by the executor.
- **Transient**: In-process traceability cache in shared.py; pipeline run_metadata in memory until persisted into result_json on success.
- **Authoritative for run attribution**: DB-backed job.result_json.provider (and optional prompt_key). **Supplementary**: execution_log events and hybrid_report when files are present.

### 1.4 Consumed by API/frontend vs internal-only

- **API/frontend**: Job summary (id, status, created_at, updated_at, error_message); position summary (including qtySource, qtyInferenceReason, qtyResolved, source_image_id, traceability_status, has_evidence, detected_summary_json); execution-log events; aisle/status error fields.
- **Internal-only**: last_stage_error.txt (read by executor to build error_message); traceability cache; detailed run_metadata beyond what is in result_json.

---

## 2. Minimum metadata contract

For each metadata family, classification:

| Metadata | Status | Notes |
|----------|--------|-------|
| **Prompt version** | Persisted when attributable (Phase 7) | When `hybrid_prompt` is set and attributable to the run, **prompt_key** is stored in result_json. Otherwise deferred; prompt attribution remains config/code derived. |
| **Provider/model** | Persisted (Phase 7) | **provider** is stored in job.result_json on successful runs. Run attribution from DB without execution_log is now possible. |
| **Parse status** | Already present and adequate | QtyParseStatus (missing/null/invalid/zero/valid_positive) on ProductRecord; qty_parse_status persisted and derivable in detected_summary. |
| **Qty inference reason** | Already present and adequate | qty_inference_reason on ProductRecord; qtyInferenceReason in API when qty_source=inferred. |
| **Merge/consolidation** | Present but implicit | qty_source=consolidated; aggregated_from_ids in detected_summary_json. No separate "merge reason" enum. **Adequate** for current debugging. |
| **Artifact references** | Partially present | result_json.report_path; evidence/asset paths in DB. **Deferred**: explicit "artifacts supporting this result" list if needed. |
| **Lifecycle stage of failure** | Hardened in Phase 4 | Pipeline failures: last_stage_error gives "StageName: message", surfaced in error_message. Persist failures: error_message now prefixed with "Persist: ". Build/pre-pipeline failures: error_message is the exception (e.g. "Aisle not found", "No source assets"). |
| **Error category/stage/context** | Partially present | error_message (and aisle.error_message) carry free text; execution_log has structured events with stage/level/message. **Adequate** for current scope. |
| **Final DTO vs upstream** | Documented in stage boundary | detected_summary_json holds upstream blobs; ProductRecord and position response carry resolved qty and provenance. See §3. |

---

## 3. Stage boundary for regression analysis

Explicit layers for diagnosing where a regression occurred:

1. **Raw model/provider output**  
   - **Where**: Analysis provider response (in-memory); not stored verbatim. Execution log may log "AnalysisStage" success/failure and provider name.  
   - **Diagnosis**: If execution_log shows AnalysisStage failure or last_stage_error is "AnalysisStage: ...", the failure is at raw output or parse.

2. **Parsed/interpreted output**  
   - **Where**: Entity list after global analysis parse and entity resolution; written into hybrid_report.json (entities with source_image_id, quantities, traceability_status, etc.).  
   - **Diagnosis**: hybrid_report.json is the first persisted artifact of parsed output. Parse/validation errors (e.g. GlobalAnalysisParseError) are written to last_stage_error as "EntityResolutionStage: ..." or similar.

3. **Consolidation / merge / normalization**  
   - **Where**: Quantity resolution (resolve_final_qty, qty_source, qty_parse_status); SKU-level consolidation (aggregated_from_ids, final_quantity in report); traceability validation. Reflected in hybrid_report and then in persist.  
   - **Diagnosis**: ProductRecord.qty_source, qty_inference_reason, qty_parse_status; detected_summary_json.qty_final, qty_source, aggregated_from_ids. If raw report looks correct but final qty wrong, compare report entity vs ProductRecord and detected_summary.

4. **Persisted DB representation**  
   - **Where**: positions, product_records, evidences (and optionally raw_label/normalized_label for backfill).  
   - **Diagnosis**: Persist failures surface as "Persist: ..." in job.error_message. Compare hybrid_report.json entities to DB rows for the same job to see if persistence altered values.

5. **API-exposed result DTO**  
   - **Where**: shared.position_to_summary, status_response_from_result, aisle_to_response. Builds PositionSummaryResponse (qty, qtySource, qtyInferenceReason, source_image_id, traceability_status, etc.) from Position + ProductRecord + optional traceability enrichment from hybrid_report.  
   - **Diagnosis**: If DB has correct values but API response differs, the bug is in shared mappers or enrichment (e.g. _enrich_position_traceability_from_report, _qty_contract_from_product).

6. **Frontend-visible mapped result**  
   - **Where**: frontend positionToResult mappers, jobStatus helpers.  
   - **Diagnosis**: If API response is correct but UI wrong, the bug is in frontend mappers or display (e.g. qtySource fallback, traceability_status → UNVALIDATED).

**Overloaded fields**: detected_summary_json is both a business blob (SKU, quantities, traceability) and a debugging carrier (qty_final, qty_source, entity_uid). ProductRecord is the authority for qty and provenance; detected_summary_json is secondary and used for enrichment and legacy fallback.

**Reliable for regression**: Job status and error_message; execution_log events (when present); last_stage_error content; ProductRecord qty_source, qty_inference_reason, qty_parse_status; position source_image_id and traceability_status (from persist or enrichment). Best-effort: execution_log and hybrid_report when files are missing or evicted.

**Phase 7 clarification**: Hybrid-report traceability enrichment (`source_image_id`, `traceability_status`, `source_image_original_filename`) is **non-authoritative metadata**; when `hybrid_report.json` is missing, list/detail still return 200 with DB-backed result truth and only those optional fields degrade to null. HEIC normalized preview with an explicit `job_id` may fall back to the aisle’s latest job; that fallback is **best-effort only** and must not be interpreted as exact-run fidelity (see `ARTIFACT_HISTORICAL_READ_BOUNDARY.md`).

---

## 4. Error context and diagnosability

### 4.1 Current behavior

- **Lifecycle errors**: Job failure → job.error_message and aisle.error_message (and error_code, retryable). Cancel → job.error_message set to reason (e.g. "Job canceled before execution"). Truncated at 2048 chars where applicable.
- **Pipeline execution errors**: Pipeline writes last_stage_error.txt ("StageName: message") and execution_log error events. On exit_code != 0, executor reads last_stage_error and sets error_message to that text (plus exit code when no last_stage_error). On uncaught exception in executor (e.g. build input, persist), error_message is str(exception).
- **Persist failures**: Previously the exception was passed through as-is. **Phase 4 change**: Persist failures now set error_message to `"Persist: {exception_message}"` so the failing stage is explicit in the DB and API.
- **Artifact/preview/log read failures**: Execution-log endpoint returns 200 with empty events when run_dir or file is missing. HEIC/normalized path resolution returns structured failure reasons (e.g. job_run_dir_missing, manifest_missing); these are not currently surfaced as HTTP error bodies but can be logged or used internally.

### 4.2 Minimal improvements made in Phase 4

- **Executor**: When the persist use case raises, the executor catches the exception, logs it to the execution log, calls `_fail_job_and_aisle(job_id, aisle, "Persist: {exception}")` so job and aisle get the stage-prefixed error_message, then returns (does not re-raise). The outer generic exception handler is therefore not involved for persist failures; the documented "Persist: ..." contract is guaranteed on the dedicated persist-failure path.

### 4.3 What remains acceptable without redesign

- Generic exception messages for build-input failures (e.g. "Asset file not found", "Aisle not found") already identify the cause. No need to add a "BuildInput:" prefix unless we introduce more build steps.
- Execution-log and last_stage_error are best-effort; if the process crashes before writing, error_message may be generic. Documented in §1 and in JOB_LIFECYCLE.

---

## 5. How to investigate failures/regressions

1. **Identify the run**: Use job id from list/status or execution-log URL. Load job from DB (status, error_message, result_json).
2. **Locate the stage**: If error_message starts with "Persist:", failure was in persist. If it contains "StageName: message" (from last_stage_error), failure was in that pipeline stage. Otherwise, failure was pre-pipeline (e.g. no assets, aisle not found) or in pipeline without a written last_stage_error.
3. **Inspect execution log**: GET .../jobs/{job_id}/execution-log. Events list stage, level, message, and optional payload. Use to see which stage ran last and whether analysis/persist completed.
4. **Inspect artifacts (if present)**: hybrid_report.json for parsed entities and quantities; input_manifest.json for input photos. Compare report entities to DB positions/product_records for the same job.
5. **Compare layers**: If report looks correct but DB wrong → persist or mapping bug. If DB correct but API wrong → shared mapper or traceability enrichment. If API correct but UI wrong → frontend mapper.
6. **Quantity provenance**: Use ProductRecord.qty_source, qty_inference_reason, qty_parse_status and position summary qtySource, qtyInferenceReason, qtyResolved to see whether qty was detected, inferred, or consolidated and why.

---

## References

- Lifecycle: `docs/3.2.5/JOB_LIFECYCLE_3_2_5.md`
- Execution log: `backend/src/pipeline/execution_log.py`
- Executor: `backend/src/infrastructure/pipeline/v3_job_executor.py`
- Shared mappers: `backend/src/api/routes/v3/shared.py`
- Quantity resolution: `backend/src/domain/quantity/resolution.py`
- Traceability: `backend/src/domain/traceability.py`, `backend/src/infrastructure/pipeline/v3_report_mapper.py`
