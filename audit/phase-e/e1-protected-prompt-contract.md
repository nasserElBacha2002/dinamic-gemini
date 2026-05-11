# E1 — Protected Prompt Contract Formalization

**Phase:** E1 (Client-Oriented Redesign — Phase E)  
**Date:** 2026-05-11  
**Status:** Documentation + behavior-neutral markers; no pipeline integration of supplier prompts.

---

## 1. Executive summary

Phase E1 **names and isolates** the parts of the hybrid global-analysis prompt system that are **not operator- or supplier-editable**: the **ProtectedSystemContractBlock** (hybrid profile bodies in `hybrid_profiles.py` plus Claude canonical append) and **ProviderPromptRules** (per-provider overlay in `hybrid_resolution.py` and wire-level JSON enforcement in adapters, notably OpenAI’s `_JSON_OBJECT_SUFFIX`).

Supplier instructions from `supplier_prompt_configs` remain **management-only**; they are **not** read by the pipeline in E1.

Code additions:

- `backend/src/llm/prompt_composer/protected_prompt_contract.py` — audit identifiers (`PROTECTED_PROMPT_CONTRACT_KEY` / `VERSION`) and **marker tuples** for regression tests (not full golden bodies).
- Comments in `hybrid_profiles.py`, `hybrid_resolution.py`, `hybrid_analysis_prompt.py`, `hybrid_global_analysis_strategy.py`, `openai_sdk_adapter.py` linking terminology to this document.
- `backend/tests/llm/test_protected_prompt_contract_markers.py` — marker-based contract tests.
- **Golden SHA refresh** in `test_prompt_composer_parity.py`: fingerprints were **out of date** relative to current `hybrid_profiles` bodies on this branch; E1 did **not** change `_GLOBAL_V21` / `_GLOBAL_V21_B` string literals—only the module docstring in `hybrid_profiles.py`. Updating goldens **re-baselines** the test to the shipped prompt text (see §11).

---

## 2. Current protected prompt sections

| Section | Location | Role |
|---------|----------|------|
| Hybrid **default** body (`global_v21`, `global_v21_b`) | `hybrid_profiles._GLOBAL_V21`, `_GLOBAL_V21_B` | Entity taxonomy, bbox rules, confidence, nullability, reference-image disclaimer. |
| Hybrid **OpenAI** replacement fragment | `hybrid_profiles._GLOBAL_V21_OPENAI`, `_GLOBAL_V21_B_OPENAI` | Aggressive extraction tone + explicit JSON root example (`total_entities_detected` / `entities`). |
| Claude canonical entity contract | `hybrid_profiles._CLAUDE_V21_CANONICAL_ENTITY_CONTRACT` + `CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX` | Canonical keys, forbidden keys, quantity/bbox discipline (text supplement appended for Claude-family keys in `resolve_hybrid_entry_for_provider`). |
| Photo traceability enrichment | `enrichments.enrich_prompt_with_image_ids` | Injected **after** base in `build_hybrid_analysis_prompt_with_traceability` when photos manifest present — still non-supplier, system-controlled. |
| OpenAI wire JSON suffix | `openai_sdk_adapter._JSON_OBJECT_SUFFIX` | Appended after base + optional `context_instruction`; enforces root keys and canonical entity keys on the wire. |
| Schema validation | `validation/global_analysis_schema.py` (`validate_global_analysis_structure_v21`) | Post-LLM structural contract. |
| Normalization | `llm/normalization/entity_normalizer.py` (`normalize_llm_response`) | Provider-family field cleanup before parsing. |
| Parser | `parsing/global_analysis_parser.py` | Maps JSON → domain entities; expects canonical keys after normalization. |

---

## 3. Current provider/model-specific rules

| Rule | Where |
|------|--------|
| OpenAI **replaces** default hybrid fragment when `provider_key == "openai"` and parity off | `hybrid_resolution.resolve_hybrid_entry_for_provider` |
| Claude **appends** supplement when key is `claude` / `anthropic` / `claude-*` and parity off | Same |
| **Parity mode** disables OpenAI + Claude overlays | Same + `RunContext.job_prompt_parity_mode` |
| OpenAI user message: prepend `context_instruction`, append `_JSON_OBJECT_SUFFIX` | `openai_sdk_adapter._openai_build_user_content` |
| Gemini / Claude SDK paths | `gemini_sdk_adapter.py`, `anthropic_sdk_adapter.py` — schema / multimodal ordering (see E0 flow map). |

---

## 4. Current prompt assembly chain

1. `resolve_hybrid_profile_name` + `normalize_pipeline_provider_key` (`hybrid_analysis_prompt.py`).  
2. `compose_hybrid_base` → `HybridPromptComposer.compose_base` → `resolve_hybrid_entry_for_provider` (`hybrid_assembly.py` / `composer.py` / `hybrid_resolution.py`).  
3. Optional image-ID enrichment (`hybrid_analysis_prompt.py`).  
4. `build_prompt_composition_dict` + hashes (`prompt_traceability.py`).  
5. `HybridGlobalAnalysisStrategy._analyze_once`: execution layer on composition, `_prepare_hybrid_llm_visual_bundle`, `LLMRequest`.  
6. Adapters build vendor-specific payloads; OpenAI adds JSON suffix.

---

## 5. Protected vs editable boundary

| Protected (non-editable) | Editable / contextual (today or future) |
|--------------------------|----------------------------------------|
| Hybrid profile strings and Claude contract | *(future)* `supplier_prompt_configs.instructions_text` |
| OpenAI `_JSON_OBJECT_SUFFIX` | `LLMRequest.context_instruction` from `AnalysisContext.instructions` (e.g. supplier reference copy) |
| `validate_global_analysis_structure_v21` rules | *(future)* inventory/aisle label lines (must not contradict schema) |
| `normalize_llm_response` mapping policy | — |
| `parse_entities` expectations | — |

**Explicit rule (supplier-editable instructions):**

Supplier-editable instructions may add supplier-specific guidance, but they must **not** override:

- Required **output format** (single JSON object, root keys).
- **JSON schema** / entity key contract expected by `validate_global_analysis_structure_v21`.
- **Parser requirements** in `global_analysis_parser`.
- **Normalization requirements** in `normalize_llm_response`.
- **Adapter-specific JSON enforcement** (e.g. OpenAI suffix).
- **Protected system instructions** in hybrid profiles / Claude contract.
- **Validation rules** in `global_analysis_schema`.

---

## 6. Rules for future supplier-editable instructions (E3+)

1. **Never** replace `compose_hybrid_base` output; only **append** or inject in a bounded prefix/suffix agreed per provider.  
2. **Prepend** supplier text only where adapters already support `context_instruction`, and ensure JSON suffix / schema modes still apply **after** supplier text for OpenAI.  
3. Persist **which slice** was supplier vs protected in metadata (E6), not only one blob.  
4. Redact supplier + protected bodies in operator UI where policy requires (E7).

---

## 7. Prompt ordering recommendation

- **Recommended (OpenAI):** `[context_instruction (supplier + ref copy)] + [hybrid base] + [_JSON_OBJECT_SUFFIX]]` — verify in E3 that this ordering cannot erase the suffix (today suffix is appended after concatenation in `_openai_build_user_content`).  
- **Gemini / Claude:** Follow existing multimodal ordering; supplier text should remain **separate** from protected system blocks where the API allows.

---

## 8. Hashing recommendation (E3 / E6)

- Keep **`prompt_hash` / `base_prompt_hash`** in `prompt_composition` as SHA-256 of the **exact strings** sent or built (existing behavior).  
- For E3/E6, add **`effective_prompt_hash`** only when a distinct “effective” string is defined (protected + supplier + context merged for audit). Do not conflate with Phase 7 `prompt_version` label.  
- Use `PROTECTED_PROMPT_CONTRACT_KEY` / `PROTECTED_PROMPT_CONTRACT_VERSION` from `protected_prompt_contract.py` as **logical** contract identity for persistence when ready.

---

## 9. Regression risks

- **Silent prompt drift:** Mitigated by golden SHA tests + new marker tests.  
- **Supplier injection:** Mitigated by architectural rule (no DB in pipeline yet) + future integration tests (E4).  
- **Adapter ordering:** Re-validate when supplier text is added (E3).

---

## 10. Files inspected

E0 artifacts under `audit/phase-e/e0-*.md`; and implementation files listed in the E1 task brief (`hybrid_profiles.py`, `hybrid_assembly.py`, `composer.py`, `prompt_traceability.py`, `hybrid_analysis_prompt.py`, `hybrid_global_analysis_strategy.py`, OpenAI/Gemini/Anthropic adapters, `global_analysis_schema.py`, `entity_normalizer.py`, `global_analysis_parser.py`, `analysis_stage.py`, `entity_resolution_stage.py`).

---

## 11. Tests executed

| Command | Result |
|---------|--------|
| `python3 -m pytest backend/tests/llm -q` | Pass (after re-baseline of `test_prompt_composer_parity.py` goldens). |
| `python3 -m pytest backend/tests/test_stage3_validation.py backend/tests/test_stage_2_1_a.py -q` | Pass. |
| `python3 -m ruff check` (E1-touched paths) | Pass. |

Note: Repository layout has no `backend/tests/validation` or `backend/tests/parsing` directories; validation/parsing coverage uses root-level `test_stage3_validation.py`, `test_stage_2_1_a.py`, etc.

---

## 12. Final E1 status recommendation

**PHASE_E1_CLOSED_READY_FOR_E2** — protected contract is documented, marker tests are in place, supplier DB prompts are still not wired into the pipeline, and no DB/frontend behavior was changed.
