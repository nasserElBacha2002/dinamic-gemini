# E4 — Phase closure

**Date:** 2026-05-11  
**Final recommendation:** `PHASE_E4_CLOSED_READY_FOR_E5`

---

## 1. Summary of implementation

| Area | Change |
|------|--------|
| v3 worker + executor | Optional `ClientSupplierRepository` + `SupplierPromptConfigRepository`; `SupplierPromptResolver` built when both present; resolve before hybrid; **abort** on `resolution_status == "error"`. |
| Pipeline runner + hybrid entry | `supplier_prompt_resolution` threaded through `process_video` → `RunContext`. |
| `hybrid_analysis_prompt` | After legacy build, run `EffectivePromptComposer`; merge `effective_prompt` metadata; refresh `final_prompt_text` / `prompt_hash` when needed; append `supplier_editable_instructions_e4` to `enrichments_applied` when supplier block applied (composition validator). |
| Traceability | New composition step constant; new enrichment id constant. |
| Tests | `test_hybrid_analysis_prompt_e4_integration.py`, `test_v3_e4_supplier_resolution_abort.py`. |

---

## 2. Whether live prompt behavior changed

**Yes, conditionally for v3 worker jobs with resolver repos wired:** when an active supplier config returns non-empty instructions, the LLM **user** prompt text gains the delimited supplier section after the protected hybrid + image enrichments. **Fallback** paths remain **byte-identical** to the pre-E4 enriched prompt for the same inputs. **Non-v3** paths unchanged.

---

## 3. Paths that can apply supplier instructions

Only when **all** hold:

1. Worker passes supplier repos into `V3JobExecutor`.  
2. Resolver returns `resolution_status == "resolved"`.  
3. Trimmed `editable_instructions` non-empty.  
4. Composer sets `supplier_instructions_applied == true`.

---

## 4. Fallback behavior

Legacy null client / aisle supplier / no active config → resolver **fallback** → composer keeps protected-only text → job continues; `effective_prompt` metadata records `fallback_used` / `fallback_reason`.

---

## 5. Resolver error behavior

`resolution_status == "error"` → **`fail_job_and_aisle`** before `run_hybrid_pipeline`; error code logged; pipeline **not** invoked.

---

## 6. Effective metadata available

In-memory on **`LLMRequest.metadata["prompt_composition"]["effective_prompt"]`** (and existing composition fields). No new SQL columns in E4.

---

## 7. Validation results

From `backend/`:

- `python3 -m ruff check src tests` — pass  
- `python3 -m pytest` (slice): `test_supplier_prompt_resolver`, `test_effective_prompt_composer`, `test_hybrid_analysis_prompt_e4_integration`, `test_v3_e4_supplier_resolution_abort`, `test_v3_job_executor_coordination`, `test_protected_prompt_contract_markers`, `test_prompt_composer_parity` — **57 passed** (session run with coverage enabled in environment)

---

## 8. Remaining observations

- Multi-provider fan-out may reuse a single pre-job resolution; tighten in a later phase if per-provider supplier scopes are required.  
- `effective_prompt` does not duplicate full supplier instruction text (privacy).

---

## 9. Whether E5 can start

**Yes** — supplier reference images / pipeline resolution (E5 scope per roadmap) can proceed; E4 does not block.

---

## 10. Recommended next phase

**E5 — Supplier reference image resolution in pipeline** (per roadmap).
