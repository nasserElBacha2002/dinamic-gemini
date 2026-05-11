# E6 — Read-only traceability audit (pre-implementation snapshot + E6 resolution)

**Scope:** Execution logs, `RunContext`, `JobInput.metadata`, prompt composition metadata, hybrid report artifacts, E4/E5 observability.  
**Canonical path:** `audit/phase-e/` (same family as E5 closure docs).

## 1. Where are `inventory_id` and `aisle_id` sourced for v3 jobs?

- Domain: `Aisle.inventory_id`, `Aisle.id`.
- **E6 fix:** `V3ProcessAislePipelineRunner.build_pipeline_input` now copies them into **`JobInput.metadata["inventory_id"]`**, **`["aisle_id"]`** alongside `analysis_context`.
- `RunContext.emit_stage_event` reads **`(job_input.metadata or {}).get("inventory_id" / "aisle_id")`** and passes them to `ExecutionLogWriter.structured_event`.
- **E6 enhancement:** If metadata lacks IDs, **`RunContext._execution_log_inventory_aisle_ids`** falls back to **`supplier_prompt_resolution.inventory_id` / `.aisle_id`** when present.
- Worker bootstrap (`V3JobExecutor._v3_begin_run_monitoring`) already passed aisle/inventory into `structured_event` directly for worker events.

## 2. Where are stage events emitted?

- **`RunContext.emit_stage_event`** → `ExecutionLogWriter.structured_event` (pipeline stages).
- **`HybridInventoryPipeline`** stages call `emit_stage_event` (InputPreparation, FrameAcquisition, Analysis, …).
- **`multi_provider_analysis_execution`** emits branch events on the same `RunContext`.
- **`V3JobExecutor`** uses `exec_log.structured_event` for worker/heartbeat (separate from pipeline `RunContext` until hybrid run attaches `execution_log` to context).

## 3. Why did some stage events log `"inventory_id": null, "aisle_id": null`?

- **Root cause:** v3 `JobInput.metadata` previously contained only **`analysis_context`**, so `emit_stage_event` read `None` for both keys during the hybrid pipeline.

## 4. Which events already included correct IDs?

- Worker launch / heartbeat paths in `V3JobExecutor` that pass `req.aisle.inventory_id` and `req.aisle_id` explicitly to `structured_event`.

## 5. Where is `prompt_composition` generated?

- **`build_hybrid_analysis_prompt_with_traceability`** (`hybrid_analysis_prompt.py`) builds the construction-time dict; **`EffectivePromptComposer`** augments `effective_prompt` subtree; execution layer merges provider/model via **`apply_execution_layer_to_composition`**.

## 6. Where is `prompt_composition` attached to `LLMRequest.metadata`?

- **`HybridGlobalAnalysisStrategy._analyze_once`** merges composition into the request metadata (same object propagated to **`build_run_metadata`** for job `result_json`).

## 7. Where is the `Analysis request prepared` payload emitted?

- **`HybridGlobalAnalysisStrategy._analyze_once`**, via `execution_log.info` / structured payload including **`attachment_summary`**, **`visual_reference_attachments`**, and redacted **`prompt_composition`** from **`prompt_composition_summary_for_execution_log`**.

## 8. Which artifacts include prompt / supplier / reference traceability?

| Surface | Contents (E6) |
|--------|----------------|
| **execution_log.jsonl** | Redacted `prompt_composition` summary including **`effective_prompt`** subtree (no supplier instruction body); `prompt_text_sha256` / lengths; attachment summary |
| **run_metadata** (job `result_json`) | Full `prompt_composition` blob when analysis returns it; `visual_reference_context` |
| **hybrid_report.json** | **E6:** optional **`supplier_traceability`** (redacted supplier prompt resolution + E5 reference metadata from `AnalysisContext.metadata`) |
| **JobInput.metadata** | `analysis_context` (serialized), **`inventory_id`**, **`aisle_id`** |

## 9. Is the full supplier editable instruction body stored outside the prompt string?

- **Not** in `effective_prompt` composition subtree (by design in `_effective_prompt_composition_subtree`).
- **Not** in the new **`supplier_traceability`** report block.
- It appears only in the **assembled prompt text** (`LLMRequest.prompt` / composition `final_prompt_text` per existing Phase 6 policy).

## 10. Which tests cover this?

- **`tests/pipeline/test_hybrid_analysis_prompt_e4_integration.py`** — E4 composition + `LLMRequest` metadata.
- **`tests/pipeline/test_e6_traceability_metadata.py`** — E6: IDs, instruction spacing, log summary `effective_prompt`, secret-not-in-metadata, attachments, report block.
- **`tests/application/services/test_aisle_analysis_context_builder.py`** — instruction spacing + E5 metadata.
- **`tests/infrastructure/pipeline/test_v3_process_aisle_pipeline_runner.py`** — `inventory_id` / `aisle_id` on `JobInput.metadata`.
