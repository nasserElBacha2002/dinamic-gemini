# G6.1 — Backend fallback enforcement

## 1. Executive summary

**Status: `G6_1_READY_FOR_G6_2`**

Missing **active** `supplier_prompt_configs` row for a resolved **client_supplier_id** + provider/model scope now returns **`resolution_status="error"`** with **`NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`** (default). **`V3JobExecutor`** fails the job **before** the hybrid pipeline with an explicit message including supplier id and provider/model. **Emergency** continuation with protected-base-only prompts is available via **`V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK=true`** (maps to previous fallback behavior + auditable `fallback_used`).

## 2. Policy implemented

| Scenario | Behavior |
| --- | --- |
| Client-oriented aisle, no matching active config | **Error** (fail job) unless env override |
| `V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK=true` | **Fallback** (legacy emergency; metadata `fallback_used=true`) |
| Inventory without client / aisle without supplier | **Fallback** unchanged (legacy drift tolerance) |

## 3. Backend changes

- **`supplier_prompt_resolver.py`**: `resolve(..., allow_missing_supplier_prompt_fallback=False)`; **`SupplierPromptResolutionErrorCode.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`**.
- **`grouped_settings.py` / `PipelineVisionSettings`**: **`v3_allow_missing_supplier_prompt_fallback`** ← **`V3_ALLOW_MISSING_SUPPLIER_PROMPT_FALLBACK`**.
- **`v3_job_executor.py`**: passes flag from settings; **`_supplier_prompt_resolution_failure_message`** for clearer failure strings (especially `NO_ACTIVE_SUPPLIER_PROMPT_CONFIG`).
- **`.env.example`**: documents emergency env var.

## 4. Error handling

- Failed jobs use **`fail_job_and_aisle`** with a descriptive string — **not** a generic 500 from FastAPI (worker-side failure path).

## 5. Metadata behavior

- On emergency fallback, composition still records **`fallback_used`** / **`fallback_reason`** as before.
- On error path, hybrid pipeline does not run — no new composition row for that attempt.

## 6. Tests updated

- **`tests/application/test_supplier_prompt_resolver.py`**: default missing-config ⇒ **error**; new test for **`allow_missing_supplier_prompt_fallback=True`** ⇒ fallback; **`test_never_resolves_config_from_other_supplier`** ⇒ **error**.

## 7. Validation results

See **`audit/raw/phase-g/g6-3-validation.txt`**.

## 8. Risks / observations

- Operators must create/activate supplier prompts before processing in normal mode.
- Emergency env flag should be **off** in production unless explicitly approved.
