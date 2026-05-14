# global_v22 — controlled default activation (Phase 4)

**Date:** 2026-05-13

## New default behavior

- **Constant:** `DEFAULT_HYBRID_PROMPT_PROFILE = "global_v22"` in `backend/src/llm/prompt_composer/hybrid_assembly.py`.
- **Settings / env:** `HYBRID_PROMPT` default in `grouped_settings` and `.env.example` is **`global_v22`** when the variable is unset.
- **Resolution:** `resolve_hybrid_profile_name` uses `settings.hybrid_prompt` with fallback `DEFAULT_HYBRID_PROMPT_PROFILE`.
- **Processing API default:** `default_prompt_key(settings)` returns `global_v22` when `hybrid_prompt` is empty.
- **Jobs:** `AisleJobLaunchService` and `StartAisleProcessingCommand` use `DEFAULT_HYBRID_PROMPT_PROFILE` when no prompt is supplied; retries use `original_job.prompt_key or DEFAULT_HYBRID_PROMPT_PROFILE`.
- **Legacy façade:** `get_hybrid_prompt()` with no profile argument composes **`global_v22`**.
- **Gemini global analyzer:** empty `_prompt_text` composes `compose_hybrid_base(DEFAULT_HYBRID_PROMPT_PROFILE, None)`.
- **Admin AI snapshot:** empty `hybrid_prompt` display fallback uses the same constant.

## Rollback

1. **Environment:** `HYBRID_PROMPT=global_v21` (or `global_v21_b`) in `.env` / deployment config.
2. **Per job / API:** Pass explicit `prompt_key: "global_v21"` on `POST .../process` (or inventory operational config as applicable).

## Root JSON contract

Unchanged: **`total_entities_detected`** + **`entities[]`**. No `positions[]` / `total_positions_detected`.

## `global_v21` availability

Profile text and registry entries are **unchanged**. Unknown profile names in `HybridPromptComposer` still fall back to **`global_v21` wire text** for backward safety (composer behavior unchanged).

## Auditing / hashes

- **Profile name** `global_v22` appears in `prompt_composition` / job metadata when selected.
- **`PROTECTED_PROMPT_CONTRACT_*`** identifiers remain **v21-named** because the **protected JSON output contract** is still the hybrid v2.1 entity shape; only instructional text differs for v22.

## Tests

- Default resolution and rollback: `test_processing_provider_resolution.py`, `test_processing_experiment_catalog_models.py`, `test_aisle_processing.py`, `test_global_v22_phase3_validation_fixtures.py`.
