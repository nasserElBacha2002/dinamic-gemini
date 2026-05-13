# H7 — Provider cost calculation implementation

**Date:** 2026-05-13  
**Scope:** Backend `llm_cost_snapshot` generation, Pydantic/API tolerance, frontend auditability + compare cost display for new `partial` status and richer pricing metadata.

---

## 1. Executive summary

Phase H7 implements **model alias → canonical catalog lookup**, **expanded pricing snapshot metadata**, **provider-aware billing usage** (Claude assumption vs old blocking ambiguity, Gemini thinking policy, OpenAI reasoning subsumption), **priced `cache_write_tokens` when `cache_write_cost_per_million` exists**, **`partial_total_cost` + `capture_status: partial`**, **`pricing_snapshot.pricing_confidence`** (`operator_approved` | `embedded_placeholder` | `unknown`), and a read-only **`validate_llm_pricing_coverage(settings)`** helper. **Embedded USD values are placeholders only**; **`capture_status: exact` is reserved for totals computed from operator-supplied catalog rows** (`LLM_PRICING_CATALOG_JSON` entries). **No provider billing APIs** are called.

---

## 2. Financial authority vs placeholders

| Source | Role |
|--------|------|
| **`LLM_PRICING_CATALOG_JSON` `entries`** | Operator-defined list prices. When the matched rate row’s `(provider, model)` key appears in this JSON, `pricing_confidence` is **`operator_approved`**. These rows are the only basis for **`capture_status: exact`** (together with no ambiguity / assumption / missing-rate notes). |
| **Embedded catalog** (`_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG`) | **Fallback / non–finance-approved placeholders** for development and bootstrapping. Matches that use only embedded rows yield **`pricing_confidence: embedded_placeholder`**. If a **full `total_cost`** is still computed, **`capture_status` is `estimated`**, with note **`usage_assumption:embedded_pricing_placeholder_not_finance_approved`**. |
| **No catalog row** | **`pricing_confidence: unknown`**, `total_cost` typically unavailable. Alias → canonical with no row for that canonical id uses **`canonical_model_without_catalog_entry:…`** (and coverage **`missing_reason: canonical_model_without_catalog_entry`**). |

**Production:** configure **`LLM_PRICING_CATALOG_JSON`** with **finance-approved** rates (and optional `aliases`). Relying on embedded prices for operational cost reporting is **not** financially authoritative.

---

## 3. What changed

| Area | Change |
|------|--------|
| `backend/src/llm/costing.py` | Aliases merged into catalog; `resolve_pricing_with_canonical` (+ `matched_catalog_key`, `alias_resolved_without_entry`); `__operator_catalog_entry_keys__` on merged catalog; `pricing_confidence`; embedded-only totals → `estimated` + placeholder assumption note; merged default `pricing_source` suffix **`dinamic_embedded_placeholders`**; `canonical_model_without_catalog_entry:…` when alias resolves to missing row; `validate_llm_pricing_coverage` uses alias flag for missing reason |
| `backend/src/api/schemas/benchmark_schemas.py` | Optional `pricing_confidence` on `LlmPricingSnapshotResponse` |
| `backend/tests/llm/test_llm_costing.py` | Assertions for confidence, embedded `estimated`, alias-without-row, coverage |
| Frontend | `LlmPricingSnapshot.pricing_confidence`; compare note + `formatCostDisplay` for canonical-without-row; i18n (es/en) |

### Before / after (representative)

**Embedded-only model with usage — before:** could surface as **`exact`** with a total. **After:** **`embedded_placeholder`**, **`estimated`**, explicit **placeholder-not–finance-approved** assumption note.

**Operator JSON row — after:** **`operator_approved`**; **`exact`** when all priced dimensions are covered and there are no ambiguity or assumption notes.

---

## 4. Model alias and pricing catalog behavior

- **Embedded catalog** includes an **`aliases`** array (initially empty). Operator JSON may define `aliases: [{ "provider", "alias", "canonical_model" }]`.
- **Merge:** `_load_pricing_catalog` merges `entries` and **`aliases`** (user overrides embedded on same `(provider, alias)` key).
- **Resolution order:** exact `(provider, model)` entry → alias match → canonical entry → provider wildcard `model: "*"` / empty.
- **Missing entry:** `pricing_entry_missing:provider=…,model=…,canonical_model=…` **or** `canonical_model_without_catalog_entry:…` when an alias mapped to a canonical id with no pricing row.

---

## 5. Provider usage normalization behavior

- **Claude:** When both `input_tokens` and `cache_read_input_tokens` are **positive**, emit **`usage_assumption:claude_input_tokens_non_cache_or_provider_reported`** (no longer `usage_dimension_ambiguous:claude_cache_read_vs_gross_input`). Totals can compute when all rates exist.
- **Gemini:** After normalize, if catalog entry has **`thinking_billed_as: "output_tokens"`**, merge candidates + thoughts into billing `output_tokens` and strip output ambiguity. If **`thinking_cost_per_million`** is set (parsed decimal), strip output ambiguity without merging unless `thinking_billed_as` requests merge.
- **OpenAI:** If `thinking_tokens <= output_tokens` and thinking > 0, zero billing thinking and add **`usage_assumption:openai_reasoning_tokens_subsumed_by_completion`**.
- **`billable_dimension_not_priced`** is emitted only when **usage > 0** and the rate is missing (avoids spurious notes on zero usage).

---

## 6. Cost status semantics

| Status | When |
|--------|------|
| `unavailable` | No usage metadata, or no `total_cost` and no `partial_total_cost` |
| `partial` | Some positive dimensions priced, at least one missing rate → `partial_total_cost` set, `total_cost` null |
| `estimated` | `total_cost` set and (`usage_dimension_ambiguous:*` or `usage_assumption:*` or **`pricing_confidence` ≠ `operator_approved`**) |
| `exact` | **`pricing_confidence` == `operator_approved`**, `total_cost` set, no ambiguity or assumption notes, no missing-rate notes |

---

## 7. Backwards compatibility

- Persisted snapshots **without** `pricing_confidence` still pass **`LlmPricingSnapshotResponse.model_validate`** (optional field defaults to `null`).
- **`llm_cost_snapshot_public_dict`** unchanged contract: extra keys flow through Pydantic v2 models with optional fields.
- Compare helpers tolerate legacy `pricing_entry_missing` **or** prefixed variant, and **`canonical_model_without_catalog_entry`**.

---

## 8. Tests

- **`tests/llm/test_llm_costing.py`:** normalization, exact/partial/unavailable builds, embedded → `estimated` + confidence, operator → `exact` + `operator_approved`, alias + wildcard resolution, alias without catalog row, cache write pricing, Gemini thinking policy, `validate_llm_pricing_coverage`, sanitize unchanged.
- **Frontend:** `compareFormatters.test.ts` for placeholder assumption and canonical-without-row notes; existing panel/compare smoke tests as applicable.

---

## 9. Remaining limitations

- **Embedded list prices** are **not** finance-approved; use **`LLM_PRICING_CATALOG_JSON`** for authoritative rates.
- **`validate_llm_pricing_coverage`** is read-only; it does not block startup (no wiring added).
- **OpenAI Responses API**–specific usage shapes remain out of scope if they differ from Chat Completions `usage`.

---

## 10. Final status

**`PHASE_H7_PROVIDER_COST_CALCULATION_READY_WITH_PRICING_CONFIDENCE`**
