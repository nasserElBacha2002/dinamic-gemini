# global_v22 — controlled validation (Phase 3)

**Date:** 2026-05-13  
**Scope:** Code-level validation of `global_v22` vs `global_v21` without live LLM or network calls.

## What was validated

1. **Fixture payloads (A–F)** under the existing v2.1 root contract (`total_entities_detected` + `entities[]`):
   - **A:** Single labeled pallet with `internal_code`, `product_label_quantity`, `source_image_id`.
   - **B:** Two entities with distinct `model_entity_id`, `internal_code`, and `source_image_id`.
   - **C:** Partial label — null `internal_code` / `product_label_quantity`, lower confidence.
   - **D:** Unlabeled pallet — `PALLET`, null product fields, traceability id present.
   - **E:** `EMPTY_PALLET` with `product_label_quantity` **null** (preferred when no printed qty).
   - **E-alt:** `EMPTY_PALLET` with `product_label_quantity` **0** (schema allows int).
   - **F:** Supplier-style fallback `product_label_quantity == 1` without `quantity_source` metadata.

2. **Pipeline stack:** Each fixture passes `validate_global_analysis_structure_v21` → `normalize_llm_response(..., "gemini")` → re-validation → `parse_entities`.

3. **Prompts (no provider execution):**
   - `compose_hybrid_base("global_v21")` ≠ `compose_hybrid_base("global_v22")`; v22 contains label-first language and required root key names; no `total_positions_detected` in v22 text.
   - OpenAI overlay for v22 still exposes `total_entities_detected` in the OpenAI fragment.
   - Image-ID enrichment and supplier append ordering unchanged (EffectivePromptComposer disclaimer intact).

## Why no live provider calls

All assertions use **deterministic** JSON fixtures and **string composition** only. No SDK clients are invoked in Phase 3 tests added for this report.

## Parser / validator / normalizer result

**Compatible:** All listed fixtures validate and parse. `normalize_llm_response` keeps `total_entities_detected == len(entities)`.

## Known limitation (F)

There is **no** `quantity_source` (or similar) on the wire contract. A model returning `product_label_quantity: 1` after supplier “default to 1” instructions is **indistinguishable** from a true single-unit label read unless a future metadata field is added.

## Recommendation on default (Phase 4)

Given parser compatibility and unchanged JSON root shape, **`global_v22` is acceptable as the configured default** for new jobs, with explicit **`HYBRID_PROMPT=global_v21` (or per-job `prompt_key`)** rollback. See `audit/global-v22-controlled-default.md`.

## Tests

Implementation: `backend/tests/llm/test_global_v22_phase3_validation_fixtures.py`.
