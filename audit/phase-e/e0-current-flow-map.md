# E0 — Current Flow Map (Inventory / Aisle → LLM → Persistence → UI)

Legend: **E?** = whether Phase E is expected to touch this step.

---

## 1. Inventory / aisle selection → job creation

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| API / use case enqueue | v3 jobs API + infrastructure executor | `V3JobExecutor` (and related) | Accepts job with `JobInput` (metadata carries inventory/aisle ids, attempt, etc.) | **Maybe** — attach client/supplier ids to metadata or columns if missing consistently. |
| Job record | DB `inventory_jobs` | Row + `result_json` | Stores lifecycle + outcomes | **Yes** — new metadata keys / columns for prompt config + fallback. |

---

## 2. Pipeline execution (orchestration)

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Hybrid orchestration | `src/pipeline/hybrid_inventory_pipeline.py` | `HybridInventoryPipeline` | Stages: input → frames → analysis → entity resolution → evidence → reporting | **Yes** — pass resolved supplier prompt into analysis / metadata. |
| Run context | `src/pipeline/context/run_context.py` | `RunContext` | job_id, settings, `analysis_context`, provider/model/prompt key fields | **Yes** — optional fields for resolved supplier prompt + fallback flags (design choice: metadata vs typed fields). |

---

## 3. Input preparation & analysis context (v3 aisle)

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Aisle context | `src/application/services/aisle_analysis_context_builder.py` | `AisleAnalysisContextBuilder.build` | Supplier reference images → `VisualReferenceContext` + fixed English instruction | **Maybe** — add supplier **DB** instructions here or in composer only. |
| Path resolve | `src/infrastructure/pipeline/v3_process_aisle_pipeline_runner.py` | `resolve_visual_reference_paths`, runner | Resolves storage paths to temp local files for worker | **Unlikely** unless reference policy changes. |

---

## 4. Prompt construction (hybrid global analysis)

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Base + traceability | `src/pipeline/services/hybrid_analysis_prompt.py` | `build_hybrid_analysis_prompt_with_traceability` | Profile + provider + enrichments + composition dict | **Yes** — integrate `EffectivePromptComposer` or extend this boundary. |
| Visual bundle | `src/pipeline/adapters/hybrid_global_analysis_strategy.py` | `_prepare_hybrid_llm_visual_bundle` | `context_instruction` from `AnalysisContext.instructions`; loads reference images | **Yes** — supplier DB instructions likely merge here or one layer below. |
| Execution metadata merge | Same file | `_analyze_once`, `apply_execution_layer_to_composition` | Adds resolved provider/model to composition | **Maybe** — add supplier prompt ids to composition dict. |

---

## 5. Reference resolution

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Resolver | `src/application/services/supplier_reference_image_resolver.py` | Resolver | DB → `VisualReferenceContext` | **Unlikely** unless policy extends. |
| Prep for LLM | `src/pipeline/services/analysis_visual_reference_prep.py` | `prepare_visual_reference_inputs` | Loads/decodes images for adapters | **Unlikely**. |

---

## 6. Provider adapter request

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| OpenAI | `src/llm/openai_sdk_adapter.py` | `_openai_build_user_content` | Builds multimodal user content; prepends `context_instruction`; appends JSON suffix | **Maybe** — ordering audit when supplier text grows. |
| Gemini | `src/llm/gemini_sdk_adapter.py` | (SDK path) | Native JSON / schema modes | **Maybe** |
| Claude | `src/llm/anthropic_sdk_adapter.py` | `_anthropic_build_message_content` | Multimodal messages | **Maybe** |

---

## 7. LLM response

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Provider errors | `src/llm/errors.py` | `LLMProviderError` | Structured failures | **Unlikely** |

---

## 8. Normalization

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Normalize | `src/pipeline/stages/analysis_stage.py` | `AnalysisStage.run` → `normalize_llm_response` | Provider-specific field cleanup | **No** (preserve behavior; add tests only). |

---

## 9. Parsing / validation

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Schema | `src/validation/global_analysis_schema.py` | `validate_global_analysis_structure_v21` | Hard contract on LLM JSON | **No** |
| Parser | `src/parsing/global_analysis_parser.py` | `parse_entities` / `parse_global_analysis` | Map JSON → domain structures | **No** |

---

## 10. Persistence

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Run metadata | `src/pipeline/run_metadata.py` | `build_run_metadata`, `build_visual_reference_context` | `visual_reference_context`, `prompt_composition`, `llm_cost_snapshot` | **Yes** — extend with fallback + supplier prompt trace + `reference_source` consistency. |
| Job executor | `src/infrastructure/pipeline/v3_job_executor.py` | Persistence of `result_json` | Writes pipeline outputs | **Yes** |

---

## 11. Frontend display

| Step | Module / file | Function / class | Responsibility | Phase E change? |
|------|----------------|-------------------|----------------|-----------------|
| Execution log UI | `frontend/src/components/ExecutionLogPanel.tsx` | Component | Shows prompts (where available), references | **Yes** — selective new fields, redaction policy. |
| Client admin | Client Detail drawers | Supplier prompt editor | CRud-ish config | Already Phase D; **Maybe** link to job debug later. |

---

## End-to-end chain (one line)

**Job enqueue → `V3JobExecutor` / aisle runner builds `RunContext` + `AnalysisContext` → `HybridInventoryPipeline` runs stages → `HybridGlobalAnalysisStrategy` composes `LLMRequest` (base prompt + context + images) → provider adapter → JSON → `normalize_llm_response` → `parse_entities` → evidence/reporting → `run_metadata` merged into `result_json` → operator may inspect `ExecutionLogPanel`.**

Phase E inserts **resolver + composer + metadata** without removing legacy fallbacks.
