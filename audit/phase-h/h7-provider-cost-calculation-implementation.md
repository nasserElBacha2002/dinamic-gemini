# H7 — Provider cost calculation implementation

**Date:** 2026-05-13  
**Scope:** Backend `llm_cost_snapshot` generation, Pydantic/API tolerance, frontend auditability + compare cost display for new `partial` status and richer pricing metadata.

---

## 1. Executive summary

Phase H7 implements **model alias → canonical catalog lookup**, **expanded pricing snapshot metadata**, **provider-aware billing usage** (Claude assumption vs old blocking ambiguity, Gemini thinking policy, OpenAI reasoning subsumption), **priced `cache_write_tokens` when `cache_write_cost_per_million` exists**, **`partial_total_cost` + `capture_status: partial`**, and a read-only **`validate_llm_pricing_coverage(settings)`** helper. **No invented list prices** were added beyond the existing embedded placeholders; operators still need **`LLM_PRICING_CATALOG_JSON`** with approved rates for production models.

---

## 2. What changed

| Area | Change |
|------|--------|
| `backend/src/llm/costing.py` | Aliases merged into catalog; `resolve_pricing_with_canonical`; Claude/Gemini/OpenAI billing helpers; `cache_write` billable dimension; capture status `exact` / `estimated` / `partial` / `unavailable`; `pricing_entry_missing:provider=…,model=…,canonical_model=…`; top-level `canonical_model`; `computed_cost.partial_total_cost` + `subtotal_cache_write`; `validate_llm_pricing_coverage` |
| `backend/src/api/schemas/benchmark_schemas.py` | Optional fields on `LlmPricingSnapshotResponse`, `LlmComputedCostResponse`, `LlmCostSnapshotResponse` for backward-compatible validation |
| `backend/tests/llm/test_llm_costing.py` | Updated expectations + new tests (alias, wildcard, cache write priced, Gemini `thinking_billed_as`, coverage helper) |
| Frontend | Types, `JobAuditabilityPanel` partial row + status label, compare formatters + run labels for partial totals, i18n (es/en) |

### Before / after (representative)

**Claude unknown model — before:** `pricing_entry_missing` and cache ambiguity could prevent a clear total. **After:** `pricing_entry_missing:provider=…,model=…,canonical_model=…`; `unavailable` when no subtotals.

**Gemini cached — before:** output vs thoughts ambiguity unless manually resolved. **After:** catalog `thinking_billed_as` / `thinking_cost_per_million` clears ambiguity for billing.

**OpenAI cached — before:** split prompt vs cached when details present. **After:** same split; missing rates yield **`partial`** with **`partial_total_cost`** when some dimensions priced.

---

## 3. Model alias and pricing catalog behavior

- **Embedded catalog** (`_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG`) now includes an **`aliases`** array (initially empty). Operator JSON may define `aliases: [{ "provider", "alias", "canonical_model" }]`.
- **Merge:** `_load_pricing_catalog` merges `entries` and **`aliases`** (user overrides embedded on same `(provider, alias)` key).
- **Resolution order:** exact `(provider, model)` entry → alias match → canonical entry → provider wildcard `model: "*"` / empty.
- **Missing entry note:** `pricing_entry_missing:provider=<p>,model=<raw>,canonical_model=<c|none>`.

---

## 4. Provider usage normalization behavior

- **Claude:** When both `input_tokens` and `cache_read_input_tokens` are **positive**, emit **`usage_assumption:claude_input_tokens_non_cache_or_provider_reported`** (no longer `usage_dimension_ambiguous:claude_cache_read_vs_gross_input`). Totals can compute when all rates exist.
- **Gemini:** After normalize, if catalog entry has **`thinking_billed_as: "output_tokens"`**, merge candidates + thoughts into billing `output_tokens` and strip output ambiguity. If **`thinking_cost_per_million`** is set (parsed decimal), strip output ambiguity without merging unless `thinking_billed_as` requests merge.
- **OpenAI:** If `thinking_tokens <= output_tokens` and thinking > 0, zero billing thinking and add **`usage_assumption:openai_reasoning_tokens_subsumed_by_completion`**.
- **`billable_dimension_not_priced`** is emitted only when **usage > 0** and the rate is missing (avoids spurious notes on zero usage).

---

## 5. Cost status semantics

| Status | When |
|--------|------|
| `unavailable` | No usage metadata, or no `total_cost` and no `partial_total_cost` |
| `partial` | Some positive dimensions priced, at least one missing rate → `partial_total_cost` set, `total_cost` null |
| `estimated` | `total_cost` set and (`usage_dimension_ambiguous:*` or `usage_assumption:*`) |
| `exact` | `total_cost` set, no ambiguity or assumption notes, no missing-rate notes |

---

## 6. Backwards compatibility

- Persisted snapshots **without** new keys still pass **`LlmCostSnapshotResponse.model_validate`** (optional fields default to `null`).
- **`llm_cost_snapshot_public_dict`** unchanged contract: extra keys flow through Pydantic v2 models with optional fields.
- Compare helpers tolerate legacy `pricing_entry_missing` **or** prefixed variant.

---

## 7. Tests

- **`tests/llm/test_llm_costing.py`:** normalization, exact/partial/unavailable builds, alias + wildcard resolution, cache write pricing, Gemini thinking policy, `validate_llm_pricing_coverage`, sanitize unchanged.
- **Frontend:** `JobAuditabilityPanel.test.tsx`, `CompareManyRunsPage.test.tsx` (smoke).

---

## 8. Remaining limitations

- **Real USD/EUR amounts** are not shipped for every SKU; deploy **`LLM_PRICING_CATALOG_JSON`** with finance-approved rows and optional aliases (e.g. `claude-opus-4-7` → canonical model key that has rates).
- **`validate_llm_pricing_coverage`** is read-only; it does not block startup (no wiring added).
- **OpenAI Responses API**–specific usage shapes remain out of scope if they differ from Chat Completions `usage`.

---

## 9. Final status

**`PHASE_H7_PROVIDER_COST_CALCULATION_READY`**
