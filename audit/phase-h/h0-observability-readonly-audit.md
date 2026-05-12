# H0 — Read-only observability audit

**Scope:** Phase H0 only — code and artifact inspection; no runtime, schema, API, pipeline, or UI behavior changes.  
**Date:** 2026-05-11  
**Repo paths cited:** relative to repository root.

---

## 1. Executive summary

The system already produces **rich, redacted observability** during a run: `execution_log.jsonl` (durable artifact) carries an `AnalysisStage` event with `payload.event_type === "analysis_request"` including `prompt_composition` (summary), attachment summaries, and optional full prompt text only when explicit settings allow. `hybrid_report.json` includes a **`supplier_traceability`** subtree (supplier prompt resolution + reference summary). The **`inventory_jobs`** row stores `provider_name`, `model_name`, `prompt_key`, `prompt_version`, and a **`result_json`** block with `visual_reference_context`, legacy-style `prompt_key` / `prompt_version` strings, optional `llm_cost_snapshot`, and durable artifact pointers.

**Critical gap:** `build_run_metadata` in `backend/src/pipeline/run_metadata.py` documents that `prompt_composition` should propagate to job `result_json`, but `V3JobExecutionStateService.mark_success` in `backend/src/infrastructure/pipeline/v3_job_execution_state.py` **does not copy** `RUN_METADATA_KEY_PROMPT_COMPOSITION` (`"prompt_composition"`) into `job.result_json`. Therefore **full prompt-composition metadata (including `effective_prompt` subtree with hashes, config id/version, fallback, warnings) is not persisted on the job row** — only inferable from **execution log** and/or **hybrid_report** artifacts when those are retained and loadable.

**Client identity:** `inventory_jobs` has no `client_id` column; client is derived via `target_id` (aisle) → aisle → inventory → `inventories.client_id`, or from structured execution log payloads (`inventory_id` in `structured_event` / analysis request context), not as a denormalized job field.

**Final status:** **`READY_FOR_H1_WITH_GAPS`**

H1 can proceed with a **RunAuditabilityView** that **aggregates existing sources** (job row + joins + hybrid_report API + execution log API) and documents null/legacy behavior. For **SQL-only metrics** and **single-query job audit rows**, additive persistence of a compact audit snapshot (or persisting `prompt_composition` into `result_json` / dedicated columns) remains a follow-on unless product accepts artifact-only truth.

---

## 2. Current observability map

| Metadata | Exists? | Where found | Persisted? | Queryable? | Notes |
|---------|---------|-------------|------------|------------|-------|
| `client_id` | Partial | `inventories.client_id` (join from job → aisle → inventory); optional in execution log `structured_event` payload (`inventory_id`, not client id directly) | Yes on inventory row | Via join / API that loads inventory | Not on `Job` entity (`backend/src/domain/jobs/entities.py`). |
| `client_supplier_id` | Yes | `aisles.client_supplier_id` (domain `Aisle` in `backend/src/domain/aisle/entities.py`); `hybrid_report.supplier_traceability.supplier_references.client_supplier_id` (`backend/src/reporting/supplier_traceability.py`) | Yes on aisle | Via join or hybrid_report | Not on job row. |
| `supplier_prompt_config_id` | Yes | `SupplierPromptResolution` → `supplier_traceability.supplier_prompt.supplier_prompt_config_id`; `prompt_composition.effective_prompt` (in-memory / logs) | In hybrid_report when run completes reporting | Via hybrid_report artifact or execution log summary | Not in `result_json` after success (see §1). |
| `supplier_prompt_config_version` | Yes | Same as above (`supplier_prompt_config_version`) | hybrid_report | Same | Same |
| `protected_template_key` (as `protected_prompt_contract_key`) | Yes | `hybrid_analysis_prompt._effective_prompt_composition_subtree` (`backend/src/pipeline/services/hybrid_analysis_prompt.py`); allowlisted in `EFFECTIVE_PROMPT_EXECUTION_LOG_KEYS` (`backend/src/llm/prompt_composer/prompt_traceability.py`) | In full `prompt_composition` in memory; in execution log `effective_prompt` subset | execution_log.jsonl; not job `result_json` | Naming: **protected_prompt_contract_key**, not `protected_template_key`. |
| `protected_template_version` (as `protected_prompt_contract_version`) | Yes | Same subtree | Same | Same | Same naming caveat. |
| `effective_prompt_hash` | Yes | Under `prompt_composition["effective_prompt"]["effective_prompt_hash"]` | execution_log summary; hybrid_report trace block does **not** duplicate full effective subtree (only supplier_prompt + supplier_references) | execution_log + in-memory | For historical job without log: **not** in supplier_traceability block. |
| `provider_name` | Yes | `Job.provider_name`; `result_json["provider"]` on success (`mark_success`); execution log `pipeline_provider` / response `provider` | Yes (`inventory_jobs.provider_name`, `result_json`) | SQL + API | Pipeline key vs resolved LLM provider distinguished in composition (`resolved_llm_provider_key`). |
| `model_name` | Yes | `Job.model_name`; inside `prompt_composition` / summary (`prompt_traceability.py`) | Yes on job row | SQL + API | |
| `supplier_reference_images_used` | Partial | `visual_reference_context.reference_ids` in `result_json` (`build_visual_reference_context` in `run_metadata.py`); `supplier_traceability.supplier_references.image_count` | `result_json` (counts/ids); hybrid_report (aggregate count) | Yes with caveats | IDs are **reference_id strings** from `AnalysisContext.visual_references`; optional `reference_source: supplier_reference_images` when any ref has `role == supplier_reference`. **Distinguishing supplier vs legacy inventory visual refs as separate persisted flags:** not modeled beyond empty refs + resolution_status on aisle builder. |
| `inventory_visual_references_used` | No (explicit) | No dedicated persisted flag in v3 path audited | N/A | N/A | Legacy table `inventory_visual_references` exists only in migrations (`0029_drop_*`); application path inspected uses supplier refs (`aisle_analysis_context_builder.py`). No explicit “used legacy inventory visual references” boolean in job/result_json. |
| `fallback_used` | Yes | `supplier_traceability.supplier_prompt.fallback_used`; `effective_prompt.fallback_used` in composition | hybrid_report (supplier_prompt); execution log allowlisted `effective_prompt` | hybrid_report + log | Not on job row / `result_json`. |
| `fallback_reason` | Yes | Same sources | Same | Same | Same |
| `warnings` | Yes | `effective_prompt.warnings` in composition (`hybrid_analysis_prompt.py`) | execution log allowlisted keys | execution log | Not persisted on job `result_json`. |
| `prompt_composition` (full) | Yes (runtime) | `build_run_metadata` adds key `prompt_composition` (`run_metadata.py`); attached to analysis result / LLM metadata | **Not** written by `mark_success` to `result_json` | execution_log summary + hybrid_report partial | Implementation vs docstring mismatch is a **persistence gap**. |
| Execution log event types | Yes | JSONL: `stage`, `level`, `message`, optional `payload`; `structured_event` adds `payload.event` | `execution_log.jsonl` durable artifact | API routes serving parsed events (see §6) | No fixed enum in `execution_log.py`; consumers match `stage` + `message` + `payload` shape. |

---

## 3. Run/job auditability assessment

| Question | Answer | Evidence |
|----------|--------|----------|
| Can a historical job explain which **client** it used? | **Indirectly yes** | Job has `target_type` / `target_id` (aisle). Resolve `aisle` → `inventory.client_id`. Not denormalized on job. |
| Can a historical job explain which **supplier** (client supplier) it used? | **Indirectly yes** | `Aisle.client_supplier_id`; also `hybrid_report.supplier_traceability.supplier_references.client_supplier_id` when report exists. |
| Can it explain which **prompt config / version**? | **Yes if artifacts exist** | `supplier_traceability.supplier_prompt` (`supplier_traceability.py`). Not in `result_json` on success. |
| Can it explain which **images** were used? | **Partially** | `result_json.visual_reference_context` has `reference_ids`, counts, `reference_source` when supplier refs present (`run_metadata.py`). Does not carry filenames in that block (attachments detailed in execution log `analysis_request`). |
| Can it explain **why fallback** happened? | **Yes if artifacts exist** | `fallback_used` / `fallback_reason` on supplier prompt resolution in hybrid_report; `effective_prompt` in execution log summary. Supplier reference **resolution_status** values on context metadata (`aisle_analysis_context_builder.py`). |
| Can it explain **provider/model**? | **Yes** | `inventory_jobs.provider_name`, `model_name`; `result_json.provider`; execution log and `prompt_composition_summary` include provider/model fields. |
| Enough for **support/debugging**? | **Mostly yes with artifacts** | Operator UI already surfaces execution log + prompt summary (`AisleObservabilityWorkspace.tsx`). Gaps: job row alone insufficient for prompt config/version/hash without loading hybrid_report or execution log; `prompt_composition` not on `result_json`. |

---

## 4. Execution log assessment

Execution log format: `backend/src/pipeline/execution_log.py` — append-only JSONL, sanitized strings (512 max unless key `prompt_text`), events are `(ts, stage, level, message, payload?)`.

| Event type/name | Payload summary | Useful for H1/H2? | Stability risk |
|-----------------|-----------------|-------------------|----------------|
| `Pipeline` / `"Job started"` | `job_id` (as `execution_id` in code path — verify caller) | Medium | Message string coupling |
| `Pipeline` / `"Job completed successfully"` | Minimal | Low | |
| `InputPreparationStage` | start/complete | Low | |
| `FrameAcquisitionStage` | paths/counts (truncated) | Medium | May evolve |
| `AnalysisStage` / `"Analysis request prepared"` | **`payload.event_type: "analysis_request"`**, `pipeline_provider`, `attachment_summary`, `primary_evidence_attachments`, `visual_reference_attachments`, **`prompt_composition`** (summary + `effective_prompt` allowlist), `prompt_text_sha256`, `prompt_text_len`, optional **`prompt_text`** | **High** | **Medium:** attachment structure and optional full prompt depend on settings (`hybrid_global_analysis_strategy.py`); large payloads possible when full prompt enabled |
| `AnalysisStage` / `"Analysis request started"` | `frames_count` | Medium | |
| `AnalysisStage` / `"Analysis request finished"` | `provider` from response | Medium | |
| `AnalysisStage` / `"Analysis request failed"` | error string (truncated) | High | |
| `structured_event` (via `RunContext.emit_stage_event`) | `job_id`, `inventory_id`, `aisle_id`, `attempt`, `event`, optional `details`, `duration_ms` | **High** for lifecycle | **Low** for core keys |
| `Persist` start/complete | aisle/job persistence markers (`v3_job_executor.py`) | Medium | |
| Other stages (`EntityResolutionStage`, `EvidenceStage`, `ReportingStage`) | stage progress | Low–medium | |

**Classification summary:** The **`analysis_request`** payload is the primary **audit-grade** event for prompt and reference attachment traceability. **`structured_event`** rows are stable for job/inventory/aisle correlation. Stage `message` string matching is a mild coupling risk for UI filters.

---

## 5. Pipeline metadata flow

1. **Inventory / Aisle:** `V3JobExecutor._v3_resolve_pipeline_inputs_or_abort` loads inventory for `client_id`, builds `AnalysisContext` via `build_analysis_context` (`v3_job_executor.py`); `AisleAnalysisContextBuilder.build` sets `metadata.reference_source`, `client_supplier_id`, `supplier_reference_resolution_status`, `supplier_reference_image_count`, resolves `visual_references` (`aisle_analysis_context_builder.py`).

2. **Prompt config resolution:** `SupplierPromptResolver.resolve` in executor before `run_hybrid_pipeline` (`v3_job_executor.py`); resolution object hung on `RunContext.supplier_prompt_resolution` for reporting.

3. **Effective prompt composition:** `build_hybrid_analysis_prompt_with_traceability` builds full `prompt_composition` including `effective_prompt` subtree (`hybrid_analysis_prompt.py`); execution layer adds provider/model (`apply_execution_layer_to_composition` in `prompt_traceability.py`).

4. **Reference images:** Embedded in `AnalysisContext.visual_references` and passed into hybrid strategy; `build_visual_reference_context` derives persisted `result_json` slice (`run_metadata.py`).

5. **Adapter request:** `hybrid_global_analysis_strategy.py` builds LLM request, logs `analysis_request` to execution log with **summary** composition.

6. **Execution log:** Written under `run_dir/execution_log.jsonl`, published as durable artifact (`worker_durable_artifact_publisher.py`).

7. **Reporting:** `ReportingStage` calls `build_supplier_traceability_report_block` → `hybrid_report.json` (`reporting_stage.py`, `supplier_traceability.py`).

8. **Persisted result / API:** `mark_success` writes **subset** of `run_metadata` to `job.result_json` only (`v3_job_execution_state.py`) — **drops `prompt_composition`**. `hybrid_report` loaded separately via `load_hybrid_report_json_for_api` (`v3_stored_artifact_access.py`). Execution log exposed via execution-log API and enrichment (`execution_log_enrichment.py`).

**Where metadata is lost:** Primary loss point is **`mark_success` not persisting `prompt_composition`** despite it being present in in-memory `run_metadata` from `_build_success_run_metadata` (`hybrid_inventory_pipeline.py` → `build_run_metadata`).

**Duplication:** Provider/model appear on job columns, in `result_json`, in execution log, and in hybrid_report supplier block (partial overlap).

---

## 6. Frontend visibility assessment

| Frontend surface | Existing metadata shown | Missing metadata | H2 candidate? |
|------------------|-------------------------|------------------|-------------|
| `AisleObservabilityWorkspace.tsx` | Execution log timeline; parsed **provider request** (`parseExecutionLogProviderRequest.ts`) with `prompt_composition`, attachments, redacted prompt; note on hybrid_report traceability | `client_id` / supplier names unless elsewhere in page; full `supplier_traceability` without loading hybrid_report API | **Yes** — primary debug host |
| `ExecutionLogPanel.tsx` | Filters, job/attempt/execution chips, prompt heading, attachment lists | Same as above | **Yes** |
| Job list / `JobSummary` (`processing_schemas.py`) | `provider_name`, `model_name`, `prompt_key`, `prompt_version`, `reference_usage` from `result_json.visual_reference_context` | Prompt config id/version, effective hash, fallback (not in summary schema) | Partial — good for list row |
| Hybrid report API (`get_job_hybrid_report` in `aisles.py`) | Full hybrid_report including `supplier_traceability` when artifact available | Not wired into all UIs by default | **Yes** for deep audit |

---

## 7. Metrics readiness assessment

| Future metric | Classification | Rationale |
|----------------|----------------|-----------|
| Runs by client | **POSSIBLE_WITH_QUERY_WORK** | Join job → aisle → inventory → `client_id`; no denormalized `client_id` on job. |
| Runs by supplier | **POSSIBLE_WITH_QUERY_WORK** | Join aisle → `client_supplier_id`; or parse hybrid_report if needed historically. |
| Failures by supplier | **POSSIBLE_WITH_QUERY_WORK** / **NEEDS_NEW_EVENT** | `failure_message` / `failure_code` on job + join; structured error taxonomy not guaranteed in SQL alone. |
| Fallbacks used | **NEEDS_NEW_PERSISTED_FIELD** or **artifact scan** | Fallback flags live in hybrid_report / execution log, **not** in `result_json` or indexed columns. |
| Missing prompt configs | **NEEDS_NEW_PERSISTED_FIELD** or **log mining** | Pre-run failure may not produce hybrid_report; resolution outcome not on job row. |
| Missing reference images | **POSSIBLE_WITH_QUERY_WORK** | `visual_reference_context.resolved`, counts, `supplier_reference_resolution_status` in metadata only on logs/hybrid_report — partial on `result_json` (counts/ids, optional `reference_source`). |
| Provider/model error rate | **READY_FROM_EXISTING_DATA** | Job columns + status support aggregation. |
| Average processing duration by client/supplier | **POSSIBLE_WITH_QUERY_WORK** | `started_at` / `finished_at` on job + joins; no precomputed rollup. |

---

## 8. Gaps and risks

### Blocking gaps

- None identified for **building an internal audit API that reads artifacts + joins**, assuming durable artifacts and hybrid_report are retained and accessible.

### Important gaps

- **`prompt_composition` not persisted on `job.result_json`** despite `build_run_metadata` documentation implying parity (`run_metadata.py` vs `v3_job_execution_state.py`).
- **`effective_prompt_hash` and related fields not in `supplier_traceability`** — historical audit requires execution log or future persistence.
- **No explicit persisted “legacy inventory visual references used”** flag in audited v3 path.
- **Client not denormalized on job** — complicates cheap SQL metrics.

### Nice-to-have gaps

- Stable **event_type enum** or version field on execution log lines (currently conventional `payload.event_type` only on analysis request).
- **ReferenceUsageSummary** (`reference_usage_schemas.py`) does not expose `reference_source` or supplier resolution status — list views omit nuance.

---

## 9. Recommended H1 implementation plan

**Recommended slice: H1 — Run auditability contract (read model)**

1. Define **`RunAuditabilityView`** (or equivalent) DTO: job identity, status, timestamps, `provider_name`, `model_name`, joined `client_id`, `client_supplier_id`, `reference_usage` from existing `result_json`, optional **`supplier_traceability`** from hybrid_report when loadable, optional **`analysis_request`** summary from execution log (last or primary), all **null-safe** for legacy jobs.

2. Implement a **mapper/service** in application layer that orchestrates: `JobRepository` + `AisleRepository` + `InventoryRepository` + existing `load_hybrid_report_json_for_api` / execution log reader ports — **no pipeline behavior change**.

3. Add **tests** for mapper: missing hybrid_report, missing execution log, legacy `result_json` without `reference_source`, succeeded vs failed jobs.

**If product requires SQL-only metrics first:** add a small **additive** `result_json` key or columns in a later migration (H1b) — **out of scope for H0**; treat as gap-driven follow-on.

---

## 10. Validation performed

| Command | Result |
|---------|--------|
| `python -m compileall src` (backend) | **Not run** — `python` not on PATH in sandbox shell. |
| `python3 -m compileall -q src` (backend) | **Failed** — `PermissionError` writing bytecode under `~/Library/Caches/...` (sandbox restriction on pyc cache). |
| `ruff check`, `pytest`, frontend `npm run typecheck` / `lint` / `build` | **Not run** in this audit session (read-only H0; environment blockers above). |

**Conclusion:** H0 validation is **documentation-only**; run the suggested commands locally or in CI with a normal Python environment to confirm green builds.

---

## References (non-exhaustive)

- `backend/src/domain/jobs/entities.py` — `Job` fields.
- `backend/src/infrastructure/pipeline/v3_job_execution_state.py` — `mark_success` → `result_json` keys written.
- `backend/src/pipeline/run_metadata.py` — `build_run_metadata`, `build_visual_reference_context`.
- `backend/src/pipeline/hybrid_inventory_pipeline.py` — `_build_success_run_metadata`.
- `backend/src/reporting/supplier_traceability.py` — hybrid_report block.
- `backend/src/pipeline/adapters/hybrid_global_analysis_strategy.py` — execution log `analysis_request`.
- `backend/src/llm/prompt_composer/prompt_traceability.py` — execution log allowlist.
- `backend/src/database/migrations/versions/0010_multi_run_job_scoping.sql` — job provider/model/prompt columns.
- `frontend/src/components/AisleObservabilityWorkspace.tsx` — operator observability UI.
