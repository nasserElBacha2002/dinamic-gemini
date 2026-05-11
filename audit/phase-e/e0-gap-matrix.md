# E0 — Gap Matrix (Phase E targets vs current codebase)

| Requirement | Current status | Files involved (representative) | Gap | Risk | Recommended phase |
|-------------|----------------|----------------------------------|-----|------|-------------------|
| Resolve client from inventory | Partial — domain/repos have client linkage; pipeline uses `JobInput.metadata` without a single typed “ClientResolver” | Inventories repos, v3 job executor, `RunContext` | No unified resolver service; nullable `client_id` | Wrong client if inferred from wrong source | **E2** SupplierPromptResolver (or shared context builder) |
| Resolve supplier from aisle | Partial — `Aisle` has `client_supplier_id`; used in `AisleAnalysisContextBuilder` | `src/domain/aisle/entities.py`, `aisle_analysis_context_builder.py`, aisle runner | Not propagated into prompt metadata or job row explicitly | Audit gaps | **E2**, **E6** |
| Resolve active supplier prompt config | **Not implemented in pipeline** — only REST + use cases | `manage_supplier_prompt_configs.py`, `sql_supplier_prompt_config_repository.py`, **not** referenced from `src/pipeline/` | No runtime load by provider/model | Feature invisible to LLM | **E2** |
| Preserve protected prompt contract | **Yes** — static profiles + validation + normalizer | `hybrid_profiles.py`, `global_analysis_schema.py`, `entity_normalizer.py` | Supplier text not yet injected | Override / prompt injection | **E1**, **E3**, **E4** |
| Compose effective prompt | Partial — `build_hybrid_analysis_prompt_with_traceability` + adapter concatenation | `hybrid_analysis_prompt.py`, adapters | No explicit “effective = protected + supplier” boundary | Hard to audit | **E3** |
| Calculate effective prompt hash | Partial — `prompt_composition` has `prompt_hash` / `base_prompt_hash` for assembled strings | `prompt_traceability.py` | No separate hash that includes post-merge supplier block only | Confusion between base vs effective | **E3**, **E6** |
| Prefer supplier reference images | **Yes for v3 aisle path** (builder + tests) | `aisle_analysis_context_builder.py`, `v3_process_aisle_pipeline_runner.py` | Other job types may differ | Inconsistent behavior across job types | **E5** (unify policy) |
| Fallback to legacy references | Still present in codebase/tests for inventory visual references | Tests, `WorkerInputArtifactResolver`, storage paths | Policy not centralized in one service | Wrong reference source | **E5** |
| Persist prompt config metadata | **No** — no supplier_prompt_config id/version in run_metadata | `run_metadata.py`, `v3_job_executor.py` | Missing fields | Non-auditable runs | **E6** |
| Persist reference usage metadata | **Partial** — `visual_reference_context` + optional `reference_source` | `run_metadata.py` | May not list all provenance fields Phase E wants | Incomplete audits | **E6** |
| Persist fallback metadata | **No** dedicated `fallback_used` / `fallback_reason` | — | Missing | Cannot explain default prompt | **E6** |
| Show debug metadata in frontend | **Partial** — execution log shows prompts/attachments | `ExecutionLogPanel.tsx` | No supplier prompt / fallback fields | Operators blind to config | **E7** |
| Validate Gemini regression | Tests exist; need focused suite after changes | `backend/tests/llm/`, pipeline tests | TBD after E4 | Regression | **E8** |
| Validate OpenAI regression | Same | `openai_sdk_adapter.py`, tests | TBD | JSON suffix / ordering | **E8** |
| Validate Claude/Cloud regression if applicable | Adapter present | `anthropic_sdk_adapter.py` | TBD | Multimodal differences | **E8** |
| Preserve `normalize_llm_response` | **Yes** | `analysis_stage.py`, `entity_normalizer.py` | None if untouched | Breaking SKU/qty mapping | **E8** (guard tests) |
| Preserve `global_analysis_parser` | **Yes** | `entity_resolution_stage.py`, `global_analysis_parser.py` | None if schema stable | Parse drift | **E8** |
| Preserve `validate_global_analysis_structure_v21` | **Yes** | adapters / gemini path | None | Invalid JSON accepted | **E8** |

---

## Summary

**Largest gaps:** runtime **supplier prompt resolution**, explicit **fallback policy** in pipeline, **job metadata** keys/columns for audit, and **frontend** surfacing of those keys — all align with planned E2–E7.

**Largest strengths:** protected hybrid profiles, **normalization + parser + schema** chain, **prompt_composition** traceability, and **supplier reference images** for v3 aisle context are already in place.
