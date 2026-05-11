# E4 — Pipeline integration (supplier prompt behind fallback)

**Date:** 2026-05-11  
**Roadmap:** Phase E — Prompt Composer + Pipeline Integration

---

## 1. Executive summary

E4 wires **v3 `process_aisle`** jobs to **`SupplierPromptResolver`** (before the hybrid run) and **`EffectivePromptComposer`** (inside **`build_hybrid_analysis_prompt_with_traceability`** after the historical hybrid base + image-ID enrichments). The string sent as **`LLMRequest.prompt`** matches the pre-E4 path when resolution is **fallback** or when supplier instructions are not applied; when resolution is **resolved** with non-empty trimmed instructions, the delimited supplier block is appended **before** any adapter-only suffixes (e.g. OpenAI JSON root requirement). **Resolver `error`** statuses **abort** the job before `run_hybrid_pipeline` with a clear message and log line — they are **not** collapsed into legacy fallbacks.

---

## 2. Integration point chosen

| Layer | Responsibility |
|--------|----------------|
| **`V3JobExecutor`** | Builds `SupplierPromptResolver` when `client_supplier_repo` + `supplier_prompt_config_repo` are injected; calls `resolve(...)`; on `resolution_status == "error"` calls `fail_job_and_aisle` and **does not** start the pipeline; otherwise passes `supplier_prompt_resolution` into `V3ProcessAislePipelineRunner.run_hybrid_pipeline`. |
| **`HybridInventoryPipeline.process_video`** | Accepts optional `supplier_prompt_resolution` kwarg; threads into **`RunContext.supplier_prompt_resolution`**. |
| **`build_hybrid_analysis_prompt_with_traceability`** | After existing composition + hashes, if context carries a resolution object: runs **`EffectivePromptComposer`**, updates `final_prompt_text` / `prompt_hash` when text changes, appends **`composition_steps`** entry `effective_supplier_prompt`, adds additive **`effective_prompt`** metadata subtree, and records **`SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID`** in `enrichments_applied` when instructions are applied (keeps `validate_prompt_composition_dict` consistent when `final != base` without image enrichments). |

Adapters, **`hybrid_profiles`**, normalizer, parser, and schema validators are **unchanged**.

---

## 3. Dependency wiring strategy

- **`jobs/worker.py`** passes `get_client_supplier_repo()` and `get_supplier_prompt_config_repo()` into **`V3JobExecutor`**.
- **`V3JobExecutor`** optional ctor args `client_supplier_repo` / `supplier_prompt_config_repo` (default `None`) preserve tests and non-worker construction without resolver wiring.

---

## 4. Runtime behavior by resolution state

| Resolver result | Pipeline | `LLMRequest.prompt` | Metadata |
|-----------------|----------|---------------------|----------|
| `fallback` | Continues | Same as pre-E4 enriched hybrid base | `effective_prompt.*` reflects fallback flags/reason |
| `resolved` + empty instructions | Continues | Same as base | Warnings include `EMPTY_SUPPLIER_INSTRUCTIONS`; config id/version echoed |
| `resolved` + non-empty instructions | Continues | Base + supplier delimiter block | `supplier_instructions_applied=true`, `effective_prompt_hash`, etc. |
| `error` | **Stops** before hybrid | N/A | `fail_job_and_aisle` message includes `Supplier prompt resolution error: {code}`; structured log |

---

## 5. Error handling policy

**Strict:** Any `resolution_status == "error"` (e.g. `CLIENT_SUPPLIER_OWNERSHIP_MISMATCH`, `AISLE_INVENTORY_MISMATCH`, `INVENTORY_NOT_FOUND`, …) **fails the v3 job** before LLM invocation. This avoids silent degradation with inconsistent client/supplier context. Legacy **fallback** reasons (`INVENTORY_WITHOUT_CLIENT`, `AISLE_WITHOUT_CLIENT_SUPPLIER`, `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`) continue processing with protected-only prompt text.

---

## 6. Metadata added (`prompt_composition`)

Additive subtree **`effective_prompt`** (JSON-serializable, no full supplier instruction body):

- `protected_prompt_contract_key` / `protected_prompt_contract_version`
- `effective_prompt_hash`
- `supplier_prompt_config_id` / `supplier_prompt_config_version`
- `supplier_instructions_applied`, `fallback_used`, `fallback_reason`
- `resolution_status`, `resolution_error_code`
- `reference_source`, `reference_image_ids` (from `AnalysisContext` when present)
- `warnings`, `sections`

Existing **`prompt_hash`**, **`base_prompt_hash`**, **`base_prompt_text`**, profile keys, and Phase 6 fields are preserved. When supplier text is applied, **`prompt_hash`** is recomputed from the new **`final_prompt_text`**.

---

## 7. Prompt ordering policy

1. Hybrid **base** (`compose_hybrid_base`)  
2. Optional **image-ID** enrichments (photos jobs)  
3. Optional **supplier-editable** block (`EffectivePromptComposer`)  
4. Adapter-only suffixes (unchanged; e.g. OpenAI appends `_JSON_OBJECT_SUFFIX` **after** `request.prompt` in the SDK adapter)

---

## 8. Files changed (summary)

- `backend/src/pipeline/context/run_context.py` — `supplier_prompt_resolution` field  
- `backend/src/pipeline/hybrid_inventory_pipeline.py` — kwargs / `_HybridRunParams` / `RunContext` threading  
- `backend/src/pipeline/services/hybrid_analysis_prompt.py` — compose + metadata + enrichment id  
- `backend/src/llm/prompt_composer/enrichments.py` — `SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID`  
- `backend/src/llm/prompt_composer/prompt_traceability.py` — `COMPOSITION_STEP_EFFECTIVE_SUPPLIER_PROMPT`  
- `backend/src/infrastructure/pipeline/v3_job_executor.py` — resolver + abort + ctor  
- `backend/src/infrastructure/pipeline/v3_process_aisle_pipeline_runner.py` — kwarg passthrough  
- `backend/src/jobs/worker.py` — repo wiring  
- `backend/src/pipeline/adapters/hybrid_global_analysis_strategy.py` — docstring only  
- Tests: `tests/pipeline/test_hybrid_analysis_prompt_e4_integration.py`, `tests/infrastructure/pipeline/test_v3_e4_supplier_resolution_abort.py`  
- This audit + `e4-closure.md`

---

## 9. Tests added

- **Pipeline:** resolved / fallback / legacy parity / OpenAI suffix absence in pipeline text / reference metadata / composition step / empty instructions / defensive error composition path.  
- **Infrastructure:** resolver error aborts before `run_hybrid_pipeline`.

---

## 10. Runtime behavior impact

- **Non-v3** or executor **without** supplier repos: unchanged (no resolution on context; prompt path identical to E3).  
- **v3 worker:** resolver runs; supplier text may change the prompt only when resolved with non-empty instructions.

---

## 11. Remaining risks

- **Multi-provider:** Resolution uses the job’s primary provider/model once; alternate provider branches reuse the same resolution (documented tradeoff).  
- **Metadata size:** `prompt_composition` still carries full prompt strings per Phase 6 policy; E6 may trim.

---

## 12. E4 final status recommendation

`PHASE_E4_CLOSED_READY_FOR_E5`
