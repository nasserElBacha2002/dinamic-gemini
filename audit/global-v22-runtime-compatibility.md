# global_v22 — runtime compatibility (phase 2)

**Date:** 2026-05-13  
**Superseded in part by Phase 4 (2026-05-13):** the **default** hybrid profile is now **`global_v22`**. See `audit/global-v22-controlled-default.md` and `audit/global-v22-controlled-validation.md`.

**Scope:** Wire and validate `global_v22` for controlled runtime use without changing the v2.1 JSON root contract (`total_entities_detected` + `entities[]`).

## 1. Selectability at runtime

| Mechanism | Behavior |
|-----------|----------|
| **Registry** | `global_v22` is present in `PROMPTS` / `registered_hybrid_prompt_keys()` (from `hybrid_profiles.py`). |
| **POST /process `prompt_key`** | `is_valid_prompt_key` delegates to `key in registered_hybrid_prompt_keys()` — `global_v22` is accepted. `resolve_start_processing_request` passes the key through unchanged when explicit. |
| **Settings default (Phase 4)** | `HYBRID_PROMPT` / `Settings.hybrid_prompt` default is **`global_v22`**; rollback **`global_v21`** via env or explicit `prompt_key`. |
| **Per-job override** | `RunContext.job_prompt_key` wins over `settings.hybrid_prompt` (existing `resolve_hybrid_profile_name` semantics). |
| **API discovery** | `prompt_profile_catalog()` includes `global_v22` so `GET .../processing-provider-options` lists it for UIs (`inventories.py`). |

No database migration was required.

## 2. Default profile

- **Phase 4 default:** `DEFAULT_HYBRID_PROMPT_PROFILE` / `HYBRID_PROMPT` unset → **`global_v22`**.
- **Rollback:** `HYBRID_PROMPT=global_v21` or per-request `prompt_key: "global_v21"`.

## 3. Parser / validator / normalizer

- **`validate_global_analysis_structure_v21`:** Accepts label-first style payloads with two `PALLET` / `EMPTY_PALLET` entities, `product_label_quantity` including **0** for empty pallet rows (integer schema).
- **`parse_entities`:** Maps `source_image_id`, `internal_code`, quantities; extra root keys are not part of this test path.
- **`normalize_llm_response`:** Reconciles `total_entities_detected` with `len(entities)`; preserves non-alias **optional** keys on entity dicts (see below).

## 4. Optional metadata on entities

| Field | Validator | Normalized entity dict | `Entity` domain |
|-------|-----------|-------------------------|-----------------|
| `label_detected`, `label_readable`, `quantity_source`, `raw_label_text`, `requires_review` | **Not rejected** (validator checks a fixed set; does not forbid extras) | **Preserved** by current normalizer (no strip of unknown keys after alias cleanup) | **Dropped** — `parse_entities` only maps known fields |

**Recommendation:** Do not rely on these fields in business logic until a later phase defines persistence and API exposure. Do not add them to the LLM prompt as required keys (Claude canonical key list remains unchanged).

## 5. Provider-specific prompt composition

- **`compose_hybrid_base("global_v22", "openai")`** uses the **`global_v22` OpenAI fragment**, not a silent downgrade to `global_v21` (regression test).
- **Claude:** Same shared canonical contract appendix as v21/v21_b (`PROMPTS["global_v22"]["claude"]` reference).
- **Supplier / traceability:** Unchanged from phase 1 — `EffectivePromptComposer` still appends after base + image-id enrichment; disclaimer text unchanged.

## 6. Tests added / touched

- `tests/application/services/test_processing_provider_resolution.py` — explicit `global_v22` with gemini and openai.
- `tests/application/services/test_processing_experiment_catalog_models.py` — catalog order and `is_valid_prompt_key`.
- `tests/llm/test_global_v22_runtime_parser_compat.py` — validator, normalizer, parser, profile resolution, OpenAI overlay for v22.
- `tests/api/test_aisles_v3_wiring.py` — `prompt_profiles` contains `global_v22`.

## 7. Risks and follow-up

- **Product default:** Switching the fleet default from `global_v21` to `global_v22` should follow sample-job validation and stakeholder sign-off.
- **`product_label_quantity: 0`:** Semantically ambiguous vs `null` for “no printed quantity”; downstream count rules should be reviewed if EMPTY_PALLET rows frequently send `0`.
- **Optional metadata:** If persisted JSON should be stripped to canonical keys only, add an explicit strip pass in the normalizer or adapter (not implemented here).
- **Future:** `positions[]` / dual parser, `quantity_source` on `Entity`, frontend display.

## 8. Verification commands (targeted)

```bash
cd backend && python3 -m pytest \
  tests/llm/test_global_v22_runtime_parser_compat.py \
  tests/llm/test_global_v22_label_first_prompt.py \
  tests/application/services/test_processing_provider_resolution.py \
  tests/application/services/test_processing_experiment_catalog_models.py \
  tests/api/test_aisles_v3_wiring.py::test_get_processing_provider_options_returns_registered_keys \
  tests/llm/test_prompt_composer_parity.py \
  tests/llm/test_protected_prompt_contract_markers.py \
  tests/pipeline/test_effective_prompt_composer.py \
  tests/test_stage_2_1_a.py::test_validate_v21_valid_passes \
  tests/llm/test_entity_normalizer.py -q --tb=short -x
```

(Run locally after edits; CI should execute the same or broader subset.)
