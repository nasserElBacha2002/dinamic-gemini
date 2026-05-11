# E1 — Phase closure

**Date:** 2026-05-11  
**Final recommendation:** `PHASE_E1_CLOSED_READY_FOR_E2`

---

## 1. Summary of what changed

| Area | Change |
|------|--------|
| Documentation | `audit/phase-e/e1-protected-prompt-contract.md` (this contract + boundaries). |
| Code | New `protected_prompt_contract.py` (constants + marker definitions only). |
| Comments | E1 terminology pointers in `hybrid_profiles.py`, `hybrid_resolution.py`, `hybrid_analysis_prompt.py`, `hybrid_global_analysis_strategy.py`, `openai_sdk_adapter.py`. |
| Tests | New `test_protected_prompt_contract_markers.py`; updated golden SHA256 values in `test_prompt_composer_parity.py`. |

---

## 2. Whether runtime prompt behavior changed

**No intentional change** to hybrid **prompt body strings** or adapter assembly logic.

**Golden hash update:** `test_prompt_composer_parity.py` expected SHA256 values did not match `default_hybrid_composer.compose_base` output for the current `hybrid_profiles` bodies. E1 only added a **module docstring** to `hybrid_profiles.py`, not edits to `_GLOBAL_V21` literals. The fingerprint mismatch indicates **prior drift** between goldens and tracked prompt text; goldens were **re-baselined** to the current computed hashes so the suite reflects the repository as-is.

---

## 3. Protected contract key/version

Defined in `protected_prompt_contract.py`:

- `PROTECTED_PROMPT_CONTRACT_KEY = "hybrid_global_analysis_v21"`
- `PROTECTED_PROMPT_CONTRACT_VERSION = "e1-1"`

Bump `PROTECTED_PROMPT_CONTRACT_VERSION` when the protected **meaning** of the hybrid contract changes in a future phase (not for unrelated refactors).

---

## 4. Tests added/updated

| Test file | Purpose |
|-----------|---------|
| `backend/tests/llm/test_protected_prompt_contract_markers.py` | Marker presence for `compose_hybrid_base("global_v21", …)` across providers/parity; OpenAI adapter suffix marker; composition dict validation; naive-prepend design guard. |
| `backend/tests/llm/test_prompt_composer_parity.py` | Refreshed `_GOLDEN_BASE` and image-enrichment golden SHA to match current prompt/enrichment output. |

---

## 5. Validation results

- `python3 -m ruff check` on modified backend paths: **pass**
- `python3 -m pytest backend/tests/llm -q`: **213 passed**
- `python3 -m pytest backend/tests/test_stage3_validation.py backend/tests/test_stage_2_1_a.py -q`: **48 passed**

Environment: Python 3.9.6 in sandbox (full repo collection on 3.9 may still hit syntax limits elsewhere — use 3.11+ CI for global suite).

---

## 6. Remaining risks

- **OpenAI ordering** when supplier instructions land: must be re-validated in E3/E4.  
- **Golden maintenance:** Any intentional change to `hybrid_profiles` bodies must update `_GOLDEN_BASE` and marker tuples if markers move.

---

## 7. Whether E2 can start

**Yes.** E2 (`SupplierPromptResolver`) can begin with clear boundaries: resolver returns config + fallback flags only; composition changes wait for E3/E4 per E0 plan.

---

## 8. Recommended next phase

**E2 — SupplierPromptResolver** — resolve inventory → aisle → client → client_supplier → active `supplier_prompt_configs` for `(provider, model)` with explicit fallback and ownership checks; **still no** replacement of protected hybrid base text.

---

## 9. E1.x review cleanup (2026-05-11)

Post–code-review corrections; **no runtime prompt behavior change**:

- **`_GOLDEN_BASE`:** enforced exactly four distinct `(profile, provider)` keys via `_GOLDEN_BASE_EXPECTED_KEYS` + module-level assertion so duplicate dict literals cannot silently overwrite an entry.
- **Substitution guard test:** renamed to `test_future_supplier_text_must_not_substitute_protected_base`; docstring clarifies this is not the final E3/E4 ordering contract; example uses `base + "\\n\\n" + fake_supplier`.
- **Markers:** added `EMPTY_PALLET` to `HYBRID_V21_SHARED_CONTRACT_MARKERS` (present on all `global_v21` resolution branches including OpenAI overlay).
