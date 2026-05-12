# E7 — Final read-only audit: Phase E (Prompt composer + pipeline integration)

**Date:** 2026-05-11  
**Purpose:** Read-only verification before Phase E closure. **E6.1 verified complete** in repo (`EFFECTIVE_PROMPT_EXECUTION_LOG_KEYS`, concise `SUPPLIER_REFERENCES_INSTRUCTION`, `test_e61_*`).

---

## 2.1 Supplier prompt resolution

| # | Question | Answer |
|---|----------|--------|
| 1 | Where is `SupplierPromptResolver` constructed? | `V3JobExecutor` when repos are wired (`v3_job_executor.py`); `SupplierPromptResolver(...)` with inventory, aisle, client_supplier, supplier_prompt_config repos. |
| 2 | Which repos are injected? | `InventoryRepository`, `AisleRepository`, `ClientSupplierRepository`, `SupplierPromptConfigRepository` (see resolver `__init__`). |
| 3 | Both repos missing? | Resolver is optional on executor (`_supplier_prompt_resolver` may be `None`); if `None`, no resolution and `supplier_prompt_resolution` stays `None` for the run. |
| 4a | `resolved` | Active config + scope OK → `EffectivePromptComposer` may append supplier block when instructions non-empty; metadata records `resolution_status`, `supplier_instructions_applied`, etc. |
| 4b | `fallback` | Protected/base hybrid text unchanged vs no-supplier path for same enrichments; `fallback_used` / `fallback_reason` in metadata. |
| 4c | `error` | **Abort before** `run_hybrid_pipeline`: `fail_job_and_aisle` and `return None` (`v3_job_executor.py` ~419–433). |
| 5 | `error` abort before LLM? | **Yes** — hybrid pipeline not invoked after error resolution. |
| 6 | Fallback byte-identical to baseline? | E4 tests assert hash/text alignment for fallback vs `supplier_prompt_resolution=None` where specified (`test_hybrid_analysis_prompt_e4_integration.py`). |
| 7 | Supplier body out of redacted metadata? | **`effective_prompt`** subtree in composition excludes editable body by construction; **E6.1** allowlist on **`prompt_composition_summary_for_execution_log`** drops unknown keys; **`supplier_traceability`** report block excludes `editable_instructions`. |

**Expected final behavior (verified by code + tests):**

- resolved + non-empty instructions → supplier block appended.  
- resolved + empty instructions → no supplier block, warning in composition (`EMPTY_SUPPLIER_INSTRUCTIONS` path).  
- fallback → protected/base unchanged vs null resolution baseline.  
- error → fail job before hybrid pipeline.

---

## 2.2 Effective prompt composition

| # | Topic | Answer |
|---|-------|--------|
| 1 | Where is `EffectivePromptComposer` called? | `build_hybrid_analysis_prompt_with_traceability` (`hybrid_analysis_prompt.py`) after base + optional image-id enrichments. |
| 2 | After protected hybrid + image IDs? | **Yes** — composition steps order: base → enrichments → `effective_supplier_prompt`. |
| 3 | `prompt_hash` recomputed when text changes? | **Yes** — when effective text differs from pre-supplier text, composition updates `final_prompt_text` and `prompt_hash` (`sha256_utf8`). |
| 4 | `effective_prompt_hash` vs final `prompt_hash` | Tests assert alignment when supplier applied (`test_hybrid_analysis_prompt_e4_integration.py`). |
| 5 | `supplier_editable_instructions_e4` enrichment | Appended to `enrichments_applied` only when `supplier_instructions_applied` (`hybrid_analysis_prompt.py`). |
| 6 | OpenAI JSON suffix | Remains adapter concern; hybrid prompt composition excludes adapter-only JSON suffix (E4 test `test_e4_openai_pipeline_prompt_excludes_adapter_json_suffix`). |

---

## 2.3 Supplier reference images

| # | Topic | Answer |
|---|-------|--------|
| 1 | `SupplierReferenceImageResolver` construction | `V3JobExecutor` builds resolver + `AisleAnalysisContextBuilder`, passed into `V3ProcessAislePipelineRunner`. |
| 2 | Canonical table/repo | `SupplierReferenceImageRepository` → **`supplier_reference_images`**. |
| 3 | Uses `aisles.client_supplier_id`? | **Yes** — `resolve_for_supplier(aisle.client_supplier_id)`; runner also `list_by_supplier` for path resolution. |
| 4 | Inventory without `client_id` | **Skips** references; metadata `fallback_inventory_without_client` (`AisleAnalysisContextBuilder`). |
| 5 | Aisle without `client_supplier_id` | **Skips**; `fallback_aisle_without_client_supplier`. |
| 6 | No active images | Empty `visual_references`; `fallback_no_active_reference_images`. |
| 7 | Missing/unreadable files | `prepare_visual_reference_inputs` / resolver paths: `resolved: false`, warning log, skip load; job continues if primary evidence exists. |
| 8 | Only `visual_reference` for LLM attachments | **`prepare_visual_reference_inputs`** uses `role: "visual_reference"` for supplier refs in request/log model. |
| 9 | Excluded from `primary_evidence` | **Yes** — primary evidence = aisle assets / frames only. |
| 10 | `SUPPLIER_REFERENCES_INSTRUCTION` only when refs exist | **Yes** — builder adds instruction only when `visual_refs` non-empty. |

---

## 2.4 Execution logs and artifacts

| # | Topic | Answer |
|---|-------|--------|
| 1 | Stage events include IDs for v3? | **Yes** after E6 — `JobInput.metadata` carries `inventory_id`, `aisle_id` from `build_pipeline_input`. |
| 2 | ID source | **`_v3_job_input_trace_metadata(aisle)`** merged into `JobInput.metadata`. |
| 3 | Fallback when metadata missing? | **`RunContext._execution_log_inventory_aisle_ids`** uses `supplier_prompt_resolution.inventory_id` / `aisle_id`. |
| 4 | `Analysis request prepared` | Includes `attachment_summary`, `visual_reference_attachments`, redacted `prompt_composition` (with allowlisted `effective_prompt`), `context_instruction`, `prompt_text_sha256` / len (unless debug full prompt). |
| 5 | No full supplier body in log summary | **E6.1** allowlist; unknown keys stripped. |
| 6 | `hybrid_report.json` `supplier_traceability` | **When applicable** — `build_supplier_traceability_report_block` after `build_hybrid_report` (`reporting_stage.py`). |
| 7 | Redacted? | **Yes** — resolution fields + E5 metadata keys only; no `editable_instructions`. |

---

## 2.5 Tests and known gaps

| Area | Tests |
|------|--------|
| E4 | `tests/pipeline/test_hybrid_analysis_prompt_e4_integration.py`, `tests/infrastructure/pipeline/test_v3_e4_supplier_resolution_abort.py` |
| E5 | `test_supplier_reference_image_resolver.py`, `test_aisle_analysis_context_builder.py`, `test_v3_process_aisle_pipeline_runner.py`, `test_v3_job_executor_analysis_context.py` |
| E6 / E6.1 | `tests/pipeline/test_e6_traceability_metadata.py` (incl. `test_e61_*`), aisle builder spacing/policy assertions |
| Reporting | `tests/test_stage_c_stages.py::test_reporting_stage_writes_hybrid_report` |

**Skipped:** Focused slice reports **1 skipped** (pre-existing in collection; not Phase E–specific without name in tail).

**Collection / import issues:**

- **`tests/test_hybrid_global_analysis_strategy_phase4.py`**: Known **circular import** when importing `HybridGlobalAnalysisStrategy` / `pipeline.providers` under some pytest orders (documented in E4/E6 work). **Mitigation:** `test_hybrid_analysis_prompt_e4_integration.py` uses **lazy import** of `_prepare_hybrid_llm_visual_bundle` inside the combined E4+E5 test to avoid import-time cycle when other tests import that module.

- **Broader `tests/application/services`**: Some unrelated modules (**capture**, **label normalization**) may **error on collection** in certain environments (`TypeError`); **not Phase E** — see E7 closure validation section.

---

## Manual runtime validation

**Not executed in this E7 audit environment.** Prior E4 manual validation remains the runtime anchor; Phase E closure relies on targeted pytest + code audit above.
