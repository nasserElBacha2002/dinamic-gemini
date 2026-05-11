# E0 — Recommended implementation plan (post-audit): E1–E9

This document proposes **sequenced** slices after E0. It is not an implementation commitment; boundaries and exact files may shift during E1 design review.

---

## E1 — Protected prompt contract formalization

- **Goal:** Name and freeze the “protected system contract” block(s) that must never be replaced by supplier-editable text; document adapter expectations (JSON suffix, schema modes).
- **Scope:** Refactor-as-documentation: constants/module boundaries, internal docs, minimal code moves if any.
- **Out of scope:** DB changes, new APIs, behavior change to live prompts.
- **Files likely impacted:** `src/llm/prompt_composer/hybrid_profiles.py`, `src/llm/prompt_composer/hybrid_assembly.py`, `src/llm/prompt_composer/prompt_traceability.py`, adapter modules (comments / small extraction only).
- **Tests:** Golden-string tests or snapshot tests for “protected block” size/hash; adapter unit tests unchanged.
- **Validation:** `ruff`, targeted `pytest` on `llm` + `pipeline` packages (Python 3.11+ CI).
- **Rollback risks:** Low if behavior-neutral.

---

## E2 — SupplierPromptResolver

- **Goal:** Given job context (inventory, aisle, provider, model), resolve `client_id`, `client_supplier_id`, and **active** `supplier_prompt_configs` row per agreed precedence (supplier+provider+model > supplier+provider > supplier+all providers/models > default).
- **Scope:** New application service + ports; wire from job executor / aisle runner only as read side.
- **Out of scope:** Changing prompt text end-to-end; SQL schema for jobs.
- **Files likely impacted:** `src/application/services/` (new), `src/infrastructure/repositories/sql_supplier_prompt_config_repository.py` (reuse), `src/infrastructure/pipeline/v3_job_executor.py`, `v3_process_aisle_pipeline_runner.py`.
- **Tests:** Resolver unit tests with memory repo; ownership negative tests (wrong client).
- **Validation:** `pytest` new module + existing pipeline smoke tests.
- **Rollback risks:** Medium — feature-flag or “dry run” logging first if desired.

---

## E3 — EffectivePromptComposer

- **Goal:** Deterministic assembly: protected contract + provider rules + supplier instructions + optional inventory/aisle labels + reference context preamble; output `effective_prompt_text` + `effective_prompt_hash` + structured slices for metadata.
- **Scope:** Pure function / small class; no LLM network calls.
- **Out of scope:** Persisting metadata (E6), UI (E7).
- **Files likely impacted:** New `src/pipeline/services/effective_prompt_composer.py` (or `src/llm/prompt_composer/`), called from `hybrid_analysis_prompt.py` or strategy layer.
- **Tests:** Table-driven tests for ordering, hash stability, empty supplier instructions, malicious-length input handling.
- **Validation:** Unit tests + ruff.
- **Rollback risks:** Low behind composer feature flag.

---

## E4 — Pipeline integration behind fallback

- **Goal:** If resolver returns active supplier instructions, pass them into `AnalysisContext.instructions` and/or composer; if none, preserve **today’s** prompt exactly (fallback_used=false).
- **Scope:** `HybridGlobalAnalysisStrategy`, `build_hybrid_analysis_prompt_with_traceability`, possibly `AnalysisStage` metadata passthrough.
- **Out of scope:** Removing legacy paths; changing normalization.
- **Files likely impacted:** `hybrid_global_analysis_strategy.py`, `hybrid_analysis_prompt.py`, `hybrid_inventory_pipeline.py`.
- **Tests:** End-to-end pipeline tests with memory supplier repo fixtures.
- **Validation:** `pytest` pipeline + infrastructure tests.
- **Rollback risks:** Medium — default path must remain identical bit-for-bit when no supplier config.

---

## E5 — Supplier reference image resolution in pipeline (policy hardening)

- **Goal:** Centralize “prefer supplier_reference_images; fallback inventory_visual_references” policy if any code path still bypasses it; align `reference_source` in metadata for all job types that support references.
- **Scope:** Reference resolver + runner only.
- **Out of scope:** Dropping legacy tables.
- **Files likely impacted:** `supplier_reference_image_resolver.py`, `v3_process_aisle_pipeline_runner.py`, `run_metadata.py`.
- **Tests:** Extend existing C7/C71 tests.
- **Validation:** `pytest` infrastructure pipeline tests.
- **Rollback risks:** Low.

---

## E6 — Execution metadata persistence

- **Goal:** Persist `supplier_prompt_config_id`, `version`, `fallback_used`, `fallback_reason`, `effective_prompt_hash`, `reference_source`, and any `protected_template_key/version` decisions — either in `result_json` subtree or additive SQL columns (team choice).
- **Scope:** Job persistence layer, migration if columns chosen.
- **Out of scope:** Frontend.
- **Files likely impacted:** `v3_job_execution_state.py`, `v3_job_executor.py`, `schema.sql` + new migration if columns.
- **Tests:** Repository persistence tests, JSON shape contract tests.
- **Validation:** `db_migrate.py validate`, `pytest`.
- **Rollback risks:** Medium for DB columns; lower for JSON-only.

---

## E7 — Frontend debug metadata visibility

- **Goal:** Surface non-sensitive metadata in `ExecutionLogPanel` or job detail (ids, versions, hashes, fallback flags, reference source). Redact protected bodies.
- **Scope:** React components + i18n.
- **Out of scope:** Editing prompts from execution UI.
- **Files likely impacted:** `ExecutionLogPanel.tsx`, types under `frontend/src/api/types`, translations.
- **Tests:** RTL component tests.
- **Validation:** `npm run typecheck`, `npm test`, `npm run lint`.

---

## E8 — Adapter / normalization regression validation

- **Goal:** Expand or run existing matrix for Gemini/OpenAI/Claude after E4; assert `validate_global_analysis_structure_v21` + `normalize_llm_response` + `parse_entities` invariants.
- **Scope:** Tests only + minimal harness fixes.
- **Out of scope:** Prompt wording changes.
- **Files likely impacted:** `backend/tests/llm/`, `backend/tests/pipeline/`.
- **Validation:** Full backend CI on Python 3.11+.

---

## E9 — Phase E final closure

- **Goal:** Documentation, audit artifact, migration playbook, feature flags removal (if any), operational checklist.
- **Scope:** Docs + cleanup.
- **Out of scope:** New features.

---

## Suggested “next phase prompt” for implementer

Use **`/implement` Phase E1** with explicit acceptance criteria from E1 section above, referencing this audit folder:

- `audit/phase-e/e0-read-only-audit.md`
- `audit/phase-e/e0-current-flow-map.md`
- `audit/phase-e/e0-gap-matrix.md`

If any environment is discovered still relying on **`global_prompt_configs`** without migration **0032**, run **corrective migration apply** first (operational), not a new code phase.
