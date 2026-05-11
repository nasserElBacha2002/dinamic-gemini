# E0 — Phase E Read-Only Audit: Prompt Composer + Pipeline Integration

**Scope:** Read-only technical audit before Phase E implementation.  
**Date:** 2026-05-11  
**Repository:** Dinamic Inventory v3.0  

---

## 1. Executive summary

The hybrid global-analysis pipeline today builds prompts from **static hybrid profiles** (`src/llm/prompt_composer/hybrid_profiles.py`) composed through `HybridPromptComposer` / `compose_hybrid_base`, with traceability metadata in `build_hybrid_analysis_prompt_with_traceability` (`src/pipeline/services/hybrid_analysis_prompt.py`). Optional **context** (instructions + reference images) is attached separately on `LLMRequest` as `context_instruction` and `context_images`, assembled in `HybridGlobalAnalysisStrategy` from `AnalysisContext` (`src/pipeline/adapters/hybrid_global_analysis_strategy.py`).

**Phase D `supplier_prompt_configs`** are implemented end-to-end for **management only**: domain, SQL/memory repositories, use cases, v3 routes under client suppliers, and Client Detail UI. There is **no import or call** from pipeline, job executor, or prompt composer to supplier prompt repositories. The canonical `schema.sql` contains **no** `global_prompt_configs` table; migration `0032_supplier_prompt_scope_correction.sql` drops that table if it exists. A **historical** migration `0031_global_prompt_configs_foundation.sql` remains in the migrations tree (observation for operators who may have applied older steps).

**Reference images for v3 aisle processing** are resolved via `SupplierReferenceImageResolver` and `AisleAnalysisContextBuilder` (`src/application/services/aisle_analysis_context_builder.py`), then path-resolved in `v3_process_aisle_pipeline_runner.py`. Job-level `run_metadata` already persists `visual_reference_context`, `prompt_composition`, and `llm_cost_snapshot` (`src/pipeline/run_metadata.py`, `src/pipeline/hybrid_inventory_pipeline.py`). There are **no** first-class fields today for `client_id`, `client_supplier_id`, supplier prompt config id/version, `fallback_used`, or `effective_prompt_hash` as distinct persisted keys (beyond hashes inside `prompt_composition`).

**Recommendation:** **PHASE_E_READY_WITH_OBSERVATIONS** — proceed to E1 with clear boundaries: introduce `SupplierPromptResolver` + `EffectivePromptComposer` without letting editable text replace protected JSON/schema instructions; preserve adapter normalization and `validate_global_analysis_structure_v21` + `normalize_llm_response` + `parse_entities` chain.

---

## 2. Current prompt construction map

| Layer | Location | Responsibility |
|--------|-----------|------------------|
| Profile registry | `src/llm/prompt_composer/hybrid_profiles.py` | Large string templates (`global_v21`, variants, OpenAI fragments). |
| Base composition | `src/llm/prompt_composer/composer.py` (`HybridPromptComposer`), `hybrid_assembly.compose_hybrid_base` | Provider-specific overlay on profile (`resolve_hybrid_entry_for_provider`). |
| Traceability assembly | `src/pipeline/services/hybrid_analysis_prompt.py` | `build_hybrid_analysis_prompt_with_traceability`: profile → normalized provider → base text → optional image-ID enrichment; builds `prompt_composition` dict. |
| Execution layer | `src/pipeline/adapters/hybrid_global_analysis_strategy.py` | Merges resolved provider/model into composition (`apply_execution_layer_to_composition`), builds `LLMRequest` with `prompt`, `context_instruction`, `context_images`. |
| Legacy single-path | `src/llm/gemini_global_analyzer.py` | Can call `compose_hybrid_base` when no injected prompt text. |
| Adapters | `src/llm/openai_sdk_adapter.py`, `src/llm/gemini_sdk_adapter.py`, `src/llm/anthropic_sdk_adapter.py` | May prepend `context_instruction`, append JSON suffix (OpenAI), build multimodal content. |

**Multiple paths:** Hybrid pipeline (primary) vs `GeminiGlobalAnalyzer` (tests/tooling-style). Phase E should treat **hybrid strategy + adapters** as canonical for production jobs.

**Tests:** Prompt composition traceability has dedicated tests under `backend/tests/llm/` (e.g. `test_prompt_version_phase7.py`); hybrid pipeline integration tests exist under `backend/tests/pipeline/` and infrastructure pipeline tests.

---

## 3. Current protected prompt contract map

| Concern | Where it lives | Notes |
|---------|----------------|-------|
| JSON entity shape / v2.1 rules | Embedded in `hybrid_profiles` strings + provider fragments | Includes bbox rules, entity taxonomy, “valid JSON only” in OpenAI variant. |
| Schema validation | `src/validation/global_analysis_schema.py` (`validate_global_analysis_structure_v21`) | Called from Gemini analyzer path and adapter flows as applicable. |
| Post-parse normalization | `src/llm/normalization/entity_normalizer.py` (`normalize_llm_response`) | `AnalysisStage.run` always normalizes after provider returns `parsed_json`. |
| Entity parsing | `src/parsing/global_analysis_parser.py` (`parse_entities`, etc.) | Downstream of analysis stage in entity resolution. |

**Risk:** Supplier-editable instructions (future) must be injected only as a **clearly bounded block** (e.g. `context_instruction` or a dedicated section) and must **not** replace `compose_hybrid_base` output or adapter JSON suffixes. Today `context_instruction` is prepended in OpenAI path before the hybrid base + suffix — Phase E should review ordering so user text cannot negate “JSON only” requirements.

---

## 4. Current LLM provider and adapter flow

| Concern | Location |
|---------|----------|
| Strategy | `HybridGlobalAnalysisStrategy` — builds `LLMRequest`, multi-provider dispatch |
| Resolver | `src/pipeline/services/pipeline_provider_resolver.py` |
| Executor harness | `src/llm/` executors (resolved per provider) |
| Metadata | `apply_job_model_name_to_llm_request_metadata`, `LLMRequest.metadata` keys from `prompt_traceability` |

Prompt **text** is generally assembled **before** the adapter; adapters may prepend context, append suffixes, and attach images.

---

## 5. Current normalization and parsing flow

1. Provider returns parsed JSON (adapters validate/coerce to varying degrees).  
2. `AnalysisStage` → `normalize_llm_response(parsed_json, provider_name)`.  
3. `EntityResolutionStage` → `parse_entities` (`global_analysis_parser`).  
4. Evidence/reporting stages consume structured entities.

**Failures:** `LLMProviderError` from providers; parse errors surface as stage failures with logging (`analysis_stage`). Tests exist for schema, normalizer, and parser modules.

---

## 6. Current reference image resolution flow

| Step | Location |
|------|----------|
| Supplier DB images | `SupplierReferenceImageResolver` + `AisleAnalysisContextBuilder.build` — `VisualReferenceContext` with role `supplier_reference` |
| Path resolution for worker | `v3_process_aisle_pipeline_runner.resolve_visual_reference_paths` + `WorkerInputArtifactResolver` |
| Bundle for LLM | `prepare_visual_reference_inputs` / `build_primary_evidence_attachments` (from `analysis_visual_reference_prep`) |
| Job metadata | `build_visual_reference_context` — may set `reference_source` = `supplier_reference_images` when role matches |

**Legacy:** Tests and storage paths still reference `inventory_visual_references` / `visual_references` for older flows; v3 aisle tests document supplier-first behavior (`test_v3_process_aisle_pipeline_runner.py`).

---

## 7. Current inventory / client / supplier context availability

| Data | Pipeline availability |
|------|------------------------|
| `inventory_id`, `aisle_id` | Present in `JobInput.metadata` and execution log events (`RunContext.emit_stage_event`). |
| `RunContext.analysis_context` | Prepared upstream for v3 aisle runs; typed `AnalysisContext`. |
| `inventories.client_id`, `aisles.client_supplier_id` | Loaded in domain/application layers for v3 job construction (see infrastructure pipeline tests); **not** currently threaded into `prompt_composition` or supplier prompt resolution (no supplier prompt DB read). |
| `RunContext.pipeline_provider_name`, `job_model_name`, `job_prompt_key` | Used for provider + profile selection. |

**Null/legacy:** Nullable `client_id` / `client_supplier_id` remain valid per roadmap; Phase E must preserve fallbacks when FKs are null.

---

## 8. Current `supplier_prompt_configs` implementation review

| Area | Finding |
|------|---------|
| Table | `supplier_prompt_configs` in `schema.sql`; nullable `provider_name` + `model_name` with scope keys and `CK_supplier_prompt_configs_valid_scope` (post–0032 model). |
| Domain | `src/domain/client_supplier/prompt_config.py` — requires `client_supplier_id`; validates model without provider is forbidden. |
| Repositories | SQL + memory implementations; scope queries by `client_supplier_id` + provider/model. |
| Use cases | `src/application/use_cases/manage_supplier_prompt_configs.py` — list/create/get active/activate. |
| API | `src/api/routes/v3/clients.py` — nested under client + supplier; optional `scope=all` for listing all-provider scope. |
| Frontend | Client Detail — `SupplierPromptConfigsModule`, drawer, form with scope selector; Admin AI Config does not own supplier prompts. |
| Pipeline | **No integration** — grep shows usage only in application/api/infrastructure repos for **config**, not runtime. |

**Phase D verdict for E0:** Config is **correctly client-supplier scoped** in active application code and schema. **Observation:** migration `0031_global_prompt_configs_foundation.sql` still exists in repo history; **0032** removes the global table — ensure deployed DBs applied **0032**.

---

## 9. Current job/run metadata persistence review

| Field / concept | Status |
|-----------------|--------|
| `visual_reference_context` | Built in `run_metadata.py`, persisted via executor into `inventory_jobs.result_json` (see `v3_job_executor` / execution state). |
| `prompt_composition` | Included in run metadata; may contain full prompt text per `prompt_traceability` module documentation. |
| `llm_cost_snapshot` | Pass-through when present. |
| `provider` / `prompt_key` / legacy `prompt_version` string | Set in `hybrid_inventory_pipeline._build_success_run_metadata`. |
| `client_id`, `client_supplier_id` on job row | **Not audited as dedicated columns** in this pass; may appear inside `result_json` or job input metadata depending on job type — **gap for Phase E**. |
| `supplier_prompt_config_id`, `effective_prompt_hash`, `fallback_used` | **Absent** as first-class persisted fields today. |
| Execution log | `execution_log.jsonl` — redacted prompt summary by default; optional full prompt via env (`DEBUG_LOG_FULL_ANALYSIS_PROMPT`). |

---

## 10. Frontend debug visibility review

| Asset | Role |
|-------|------|
| `frontend/src/components/ExecutionLogPanel.tsx` | Shows execution events, prompt heading, reference guidance, attachments; job/attempt filters. |
| Results/analytics | Job pickers (`AisleResultsJobSelector`, compare components) — focused on outcomes, not full Phase E metadata. |

**Gaps:** No UI today for supplier prompt config id/version, `fallback_used`, or explicit `effective_prompt_hash` label (though `prompt_composition` may expose `prompt_hash` if present in payload). Avoid exposing full protected system blocks in any new debug UI.

---

## 11. Gaps vs Phase E target architecture

See `e0-gap-matrix.md` for the detailed matrix. Summary: resolver, composer, supplier-instruction merge policy, metadata columns/JSON keys, frontend panels, and regression harness are **future work**.

---

## 12. Risks and blockers

| Risk | Mitigation |
|------|------------|
| User instructions override JSON contract | Keep protected block immutable; append supplier text in controlled section; keep adapter JSON suffix. |
| Ordering of `context_instruction` vs base prompt | Re-audit per provider when integrating composer. |
| DBs stuck on 0031 without 0032 | Run migration status/validate in each environment; document dependency. |
| Nullable client/supplier FKs | Resolver must return explicit fallback + auditable reason. |

**No Phase E blocker** identified for “supplier prompts not scoped to client_supplier” in **current** application + `schema.sql`.

---

## 13. Recommended E1–E9 implementation slices

See `e0-recommended-implementation-plan.md`.

---

## 14. Recommended corrective Phase D.x (if any)

- **None required for scoping** based on current code/schema.  
- **Optional D.x hygiene:** Archive or annotate migration `0031_*` in internal docs so operators do not assume a global table is part of the product (code comment only in a future non–read-only change — out of scope for E0).

---

## 15. Final recommendation

**PHASE_E_READY_WITH_OBSERVATIONS**

Proceed to **E1 — Protected prompt contract formalization** after locking: (1) injection point for supplier instructions, (2) hash strategy (`prompt_hash` vs new `effective_prompt_hash`), (3) metadata keys for job `result_json`.

---

## 16. Validation commands (read-only)

| Command | Result |
|---------|--------|
| `python3 --version` | Python 3.9.6 (sandbox) — **not** project target 3.11+; full pytest may fail on syntax in unrelated modules when collected with older interpreter. |
| `python3 -m pytest backend/tests --collect-only` | From repo root: collection begins (large suite); use project Python in CI for authoritative signal. |
| Code search | Completed for `supplier_prompt`, `global_prompt`, `prompt_composition`, `visual_reference`, `normalize_llm_response`. |

Frontend `npm run typecheck` / `lint` were **not** re-run in this E0 pass (no code changes); prior session reported green on touched areas.
