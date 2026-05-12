# E3 — Phase closure

**Date:** 2026-05-11  
**Final recommendation:** `PHASE_E3_CLOSED_READY_FOR_E4`

---

## 1. Summary of implementation

| Area | Change |
|------|--------|
| Pipeline service | `backend/src/pipeline/services/effective_prompt_composer.py`: `EffectivePromptComposer`, `EffectivePromptComposerInput`, `EffectivePromptComposition`, `compute_effective_prompt_hash`, stable supplier delimiter block + warning constants. |
| Tests | `backend/tests/pipeline/test_effective_prompt_composer.py` |
| Audit | `audit/phase-e/e3-effective-prompt-composer.md`; this file. |

The composer imports `SupplierPromptResolution` from the application layer and E1 constants from `src.llm.prompt_composer.protected_prompt_contract`. It performs **no** I/O.

---

## 2. Whether runtime prompt behavior changed

**No.** Production hybrid assembly paths (`hybrid_analysis_prompt`, adapters, `LLMRequest` fields) are unchanged. E3 is library + tests only until E4 integrates behind fallback.

---

## 3. Effective prompt hash strategy

SHA256 hex over UTF-8 bytes of `effective_prompt_text` only. Same composed string → same hash; changing supplier body changes hash; changing only non-prompt input fields (e.g. `inventory_id`) without changing resolution/protected text does not change the hash.

---

## 4. Supplier instruction ordering

Protected hybrid base is **first** (`protected_prompt_text.rstrip()` then `\n\n` then supplier block). Adapter-specific JSON suffixes remain **out of scope** for this module (E4 must order adapter wiring correctly).

---

## 5. Validation results

From `backend/` (see session log for this workspace):

- `python3 -m ruff check src tests` — pass
- `python3 -m pytest tests/pipeline/test_effective_prompt_composer.py tests/application/test_supplier_prompt_resolver.py tests/llm/test_protected_prompt_contract_markers.py tests/llm/test_prompt_composer_parity.py -q` — pass

Full `pytest tests/application` may hit **pre-existing** Python 3.9 collection issues unrelated to E3; use Python 3.11+ for full CI parity.

---

## 6. Remaining observations

- `fallback_reason` is left `None` on `resolution_status == "error"`; audit uses `warnings` + optional `RESOLUTION_ERROR_CODE:*` instead of overloading legacy fallback reason strings.

---

## 7. Whether E4 can start

**Yes.** E4 can call the composer after resolution, behind explicit fallback policy, without changing E3’s pure contract.

---

## 8. Recommended next phase

**E4 — Pipeline integration behind fallback** — invoke resolver + composer at the job/strategy boundary; route composed text into `LLMRequest` only when policy allows; preserve adapters and protected markers.
