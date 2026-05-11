# G6.0 — Prompt fallback policy audit

## 1. Executive summary

**Status: `G6_0_READY_FOR_G6_1`**

The codebase already centralized supplier prompt resolution in **`SupplierPromptResolver`** (`resolution_status`: `resolved` | `fallback` | `error`) and **`EffectivePromptComposer`** (always applies protected contract; adds supplier section only when resolved with non-empty instructions). **`V3JobExecutor`** invoked the resolver before the hybrid pipeline and previously failed only on **`resolution_status == "error"`**, allowing **`fallback`** (including missing active `supplier_prompt_configs`) to proceed with protected-base-only prompts — **silent from a job-failure perspective**. **`hybrid_analysis_prompt`** persists **`fallback_used`**, **`fallback_reason`**, **`effective_prompt_hash`**, and **`protected_prompt_contract_*`** into prompt composition metadata when the pipeline runs.

## 2. Current fallback behavior (pre-G6.1)

| Condition | Previous `resolution_status` | Pipeline impact |
| --- | --- | --- |
| No active row for supplier/provider/model scope | `fallback`, reason `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG` | Ran with protected base only |
| Inventory without `client_id` | `fallback`, `INVENTORY_WITHOUT_CLIENT` | Ran |
| Aisle without `client_supplier_id` | `fallback`, `AISLE_WITHOUT_CLIENT_SUPPLIER` | Ran |
| Resolver hard errors (not found, mismatch, invalid scope) | `error` | Job failed before pipeline |

## 3. Resolver / composer flow

1. **`SupplierPromptResolver.resolve`** loads inventory → aisle → client_supplier ownership → **`_resolve_active_with_precedence`** on **`supplier_prompt_configs`**.
2. **`EffectivePromptComposer.compose`** receives **`SupplierPromptResolution`**; never removes protected text; on `fallback` or empty supplier instructions, output equals protected prompt string (hash reflects that).

## 4. Pipeline behavior

- **`v3_job_executor._v3_hybrid_run_and_load_report`**: resolves supplier prompt, passes **`supplier_prompt_resolution`** into **`V3ProcessAislePipelineRunner`** → **`RunContext`** → hybrid prompt builder.
- **`hybrid_analysis_prompt.build_hybrid_analysis_prompt_with_traceability`**: merges traceability + effective prompt subtree (`effective_prompt` in composition JSON).

## 5. Metadata persistence

- **`prompt_composition` / `effective_prompt`**: `fallback_used`, `fallback_reason`, `supplier_prompt_config_id/version`, `resolution_status`, `resolution_error_code`, `effective_prompt_hash`, `protected_prompt_contract_key/version`.
- **`supplier_traceability`** / reporting helpers surface **`supplier_prompt`** block when present.

## 6. Frontend / debug visibility

- **`AisleObservabilityWorkspace`**: trace tab shows resolution status, config id/version, **`fallback_used`** + translated **`fallback_reason`** (keys were partially misaligned with backend enum strings before G6.2).
- **`ClientSupplierDetail`**: summary line for active prompt via **`useActiveSupplierPromptConfig`** (404 ⇒ “sin configuración activa”).

## 7. Tests covering fallback

- **`tests/application/test_supplier_prompt_resolver.py`**
- **`tests/pipeline/test_effective_prompt_composer.py`**, **`test_hybrid_analysis_prompt_e4_integration.py`**, **`test_e6_traceability_metadata.py`**
- **`tests/infrastructure/pipeline/test_v3_e4_supplier_resolution_abort.py`**

## 8. Risks and blockers

- Missing supplier prompt config was **operationally invisible** unless operators opened execution trace metadata.

## 9. Recommended G6 policy

Implement **fail-fast** for **missing active supplier prompt config** when inventory + aisle are client-oriented (supplier scope resolved), with optional **`V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK`** for emergency protected-base-only runs. Preserve **`fallback`** for legacy inventory/aisle gaps where product still allows continuation.
