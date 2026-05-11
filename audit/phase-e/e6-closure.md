# E6 closure — Traceability, logs, artifacts, metadata hardening

**Date:** 2026-05-11  
**Recommendation:** `PHASE_E6_CLOSED_READY_FOR_E7`

## 1. Executive summary

E6 fixes **null `inventory_id` / `aisle_id`** in pipeline execution log stage events for v3 aisle jobs by writing both IDs into **`JobInput.metadata`** at pipeline input build time, and adds a **non-fatal fallback** from **`supplier_prompt_resolution`** when metadata is still empty. **Execution log** redacted `prompt_composition` summaries now include the **`effective_prompt`** subtree (flags, hashes, config ids — no supplier instruction body). **`hybrid_report.json`** may include a redacted **`supplier_traceability`** block for durable audit. **Supplier reference instruction** text uses explicit sentence spacing (`evidence. They`). Tests cover IDs, spacing, metadata leakage, attachments, and the report helper.

## 2. Files changed

| Area | Path |
|------|------|
| Instruction copy | `backend/src/application/services/aisle_analysis_context_builder.py` |
| RunContext IDs | `backend/src/pipeline/context/run_context.py` |
| v3 JobInput metadata | `backend/src/infrastructure/pipeline/v3_process_aisle_pipeline_runner.py` |
| Log summary | `backend/src/llm/prompt_composer/prompt_traceability.py` |
| Report artifact | `backend/src/pipeline/stages/reporting_stage.py`, `backend/src/reporting/supplier_traceability.py` |
| Tests | `backend/tests/pipeline/test_e6_traceability_metadata.py`, `test_aisle_analysis_context_builder.py`, `test_v3_process_aisle_pipeline_runner.py` |
| Docs | `audit/phase-e/e6-readonly-traceability-audit.md`, this file |

## 3. Traceability flow after E6

1. v3 builds `JobInput` with **`metadata.inventory_id`**, **`metadata.aisle_id`**, **`metadata.analysis_context`**.  
2. Hybrid pipeline constructs **`RunContext`** with that `job_input`.  
3. Each **`emit_stage_event`** resolves IDs from metadata, then from **`supplier_prompt_resolution`** if needed.  
4. Analysis stage logs **`Analysis request prepared`** with attachment summary and redacted **`prompt_composition`** (including **`effective_prompt`**).  
5. Reporting writes **`hybrid_report.json`**; if supplier resolution or E5 reference metadata exists, merges **`supplier_traceability`**.

## 4. `inventory_id` / `aisle_id` propagation

- **Primary:** `_v3_job_input_trace_metadata(aisle)` merged into `JobInput.metadata` in **`build_pipeline_input`** (photos + video).  
- **Fallback:** **`RunContext._execution_log_inventory_aisle_ids`** uses **`SupplierPromptResolution`** when job metadata omits IDs.

## 5. E4 metadata visibility

- Unchanged prompt assembly; **`prompt_composition_summary_for_execution_log`** now copies the existing **`effective_prompt`** dict into the log summary so operators see **`supplier_instructions_applied`**, **`fallback_used`**, **`resolution_status`**, config ids, and hashes without the editable instruction text.

## 6. E5 reference metadata visibility

- Still carried on **`AnalysisContext.metadata`** (`reference_source`, `client_supplier_id`, `supplier_reference_image_count`, `supplier_reference_resolution_status`).  
- Surfaced in **`supplier_traceability.supplier_references`** on **`hybrid_report.json`** when present.

## 7. Durable artifact / log visibility

- **Primary durable operator trace:** `execution_log.jsonl` under the run directory (attachment summary, redacted prompt composition including `effective_prompt`, hashes).  
- **Secondary:** `run_metadata` / job `result_json` (existing).  
- **Secondary:** `hybrid_report.json` → **`supplier_traceability`** (redacted).

## 8. Tests added/updated

- **`test_e6_traceability_metadata.py`** — spacing, emit_stage IDs (metadata + fallback), `prompt_composition_summary` includes `effective_prompt`, unique secret not in `effective_prompt` JSON, primary vs visual attachment roles, `build_supplier_traceability_report_block`.  
- **`test_aisle_analysis_context_builder.py`** — `test_supplier_references_instruction_has_sentence_spacing_e6`.  
- **`test_v3_process_aisle_pipeline_runner.py`** — asserts `inventory_id` / `aisle_id` on v3 `JobInput.metadata`.

## 9. Validation

From `backend/`:

```bash
python3 -m ruff check src tests/pipeline/test_e6_traceability_metadata.py
python3 -m pytest tests/pipeline/test_e6_traceability_metadata.py \
  tests/application/services/test_aisle_analysis_context_builder.py \
  tests/pipeline/test_hybrid_analysis_prompt_e4_integration.py \
  tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py \
  tests/infrastructure/pipeline/test_v3_e4_supplier_resolution_abort.py \
  tests/infrastructure/pipeline/test_v3_job_executor_analysis_context.py \
  tests/test_stage_c_stages.py::test_reporting_stage_writes_hybrid_report
```

**Recorded run:** ruff OK; pytest **33 passed, 1 skipped** (~6s) on the agent slice above.

## 10. Remaining risks / debt

- **`supplier_traceability.supplier_prompt`** does not duplicate **`supplier_instructions_applied`** (that flag lives in effective prompt / composition; resolution block uses **`resolution_status`** + **`fallback_used`**).  
- **`tests/test_hybrid_global_analysis_strategy_phase4.py`** may fail collection on some Python/import orders (pre-existing circular import); E6 tests avoid importing that module.

## 11. Final recommendation

```text
PHASE_E6_CLOSED_READY_FOR_E7
```
