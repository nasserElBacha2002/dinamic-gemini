# H6 — Provider cost calculation and pricing snapshot audit

**Scope:** Read-only technical audit (no runtime or schema changes).  
**Date:** 2026-05-13  
**Focus:** Why `llm_cost_snapshot` often shows `pricing_entry_missing`, `billable_dimension_not_priced`, and `usage_dimension_ambiguous` for Claude, Gemini, and OpenAI jobs, and how that flows to Observability → Auditabilidad.

---

## 1. Executive summary

Per-job LLM cost is built in **`build_llm_cost_snapshot`** (`backend/src/llm/costing.py`) from:

1. **`raw_usage`** — provider adapters serialize SDK usage into plain `dict` fields on **`LLMResponse.usage`**.
2. **`normalize_usage(provider, raw_usage)`** — maps those fields into a neutral **`usage`** dict and appends **convention / ambiguity notes** (`usage_dimension_ambiguous:*`).
3. **Pricing catalog** — merged **embedded defaults** + optional **`settings.llm_pricing_catalog_json`** (env `LLM_PRICING_CATALOG_JSON`). Lookup is **exact `(provider, model)` string match** after lowercasing; optional **wildcard** model `"*"` per provider only.
4. **`_apply_billable_dimensions_to_subtotals`** — for each billable dimension, if usage tokens > 0 but the catalog snapshot has **no rate** for that dimension → **`billable_dimension_not_priced:<usage_key>`**. **`cache_write_tokens`** is always **`unpriced`** in code (explicit `mode == "unpriced"`) → always emits **`billable_dimension_not_priced:cache_write_tokens`** when count > 0.
5. If **no catalog entry dict** exists for `(provider, model)` → **`pricing_entry_missing`** is appended and **`total_cost`** stays **`null`** → UI shows **“No informado”** for money lines with **`total_cost_unavailable_reason: pricing_entry_missing`**.

**Primary root cause for examples like `claude-opus-4-7`:** the **embedded default catalog** only includes **`claude` + `claude-sonnet-4-20250514`** (and **`openai` + `gpt-5.4`**). There is **no alias map**: a job whose `LLMResponse.model` is `claude-opus-4-7` will **not** resolve to any entry unless the operator catalog JSON adds that exact `(provider, model)` pair (or a wildcard row).

**Secondary causes:**

- **`usage_dimension_ambiguous:claude_cache_read_vs_gross_input`** is **by design** whenever Anthropic reports both **`input_tokens`** and **`cache_read_input_tokens`** — the code cannot prove whether `input_tokens` is gross or net of cache read; **`capture_status`** cannot be **`exact`** while any `usage_dimension_ambiguous:*` note exists.
- **`billable_dimension_not_priced:*`** for input/output/cached when an entry exists but **rate fields are `null`** in the merged snapshot, or when **positive usage** exists without a matching rate key.
- **`capture_status: estimated`** with all monetary rows “No informado” is **consistent**: backend marks **estimated** whenever usage exists but the snapshot is not **exact** (missing entry, ambiguous notes, or missing pricing for billable dimensions); **`total_cost`** can still be **`null`**.

**Frontend:** Auditabilidad renders **`cost_snapshot`** as returned; it does not hide monetary fields — “No informado” reflects **`null`** / missing strings in the snapshot.

---

## 2. Current cost data flow

Ordered pipeline (actual modules):

1. **Provider HTTP/SDK response**  
   - **Gemini:** `GeminiClient._extract_usage` → `prompt_token_count`, `candidates_token_count`, `total_token_count`, `thoughts_token_count`, `cached_content_token_count` (`backend/src/llm/gemini_client.py`).
   - **OpenAI:** `_openai_completion_usage_dict` → `prompt_tokens`, `completion_tokens`, `total_tokens`, nested `prompt_tokens_details` / `completion_tokens_details` dicts (`backend/src/llm/openai_sdk_adapter.py`).
   - **Claude:** `_anthropic_message_usage_dict` → `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, etc. (`backend/src/llm/anthropic_sdk_adapter.py`).

2. **`LLMResponse`**  
   - `LLMResponse.usage` is a plain `dict` (`backend/src/llm/types.py`).

3. **Analysis result normalization**  
   - `build_analysis_result_from_llm_response` calls **`build_llm_cost_snapshot(provider=response.provider, model=response.model, raw_usage=response.usage, settings=settings)`** (`backend/src/pipeline/services/provider_analysis_result_normalization.py`).

4. **`AnalysisResult.llm_cost_snapshot`**  
   - Carried through analysis stage (`backend/src/pipeline/stages/analysis_stage.py`).

5. **`build_run_metadata(..., llm_cost_snapshot=...)`**  
   - Key **`llm_cost_snapshot`** in run metadata (`backend/src/pipeline/run_metadata.py`).

6. **Success run metadata assembly**  
   - `_build_success_run_metadata` passes snapshot from `analysis_result` (`backend/src/pipeline/hybrid_inventory_pipeline.py`).

7. **Persist on job success**  
   - `V3JobExecutionStateService.mark_success` copies `meta["llm_cost_snapshot"]` into **`job.result_json["llm_cost_snapshot"]`** (`backend/src/infrastructure/pipeline/v3_job_execution_state.py`).

8. **Auditability API**  
   - `RunAuditabilityService` + **`llm_cost_snapshot_public_dict(result_json)`** → optional **`cost_snapshot`** on GET `.../jobs/{job_id}/auditability`.

9. **Frontend**  
   - `getJobAuditability` → `JobAuditabilityPanel` cost card (`frontend/src/components/JobAuditabilityPanel.tsx`).

---

## 3. Provider raw usage capture

### 3.1 Claude / Anthropic

**Capture:** `_anthropic_message_usage_dict` prefers `usage.model_dump(exclude_none=True)`; else copies scalar keys including **`input_tokens`**, **`output_tokens`**, **`cache_creation_input_tokens`**, **`cache_read_input_tokens`**.

**Normalization (`normalize_usage` + `_apply_claude_cache_conventions`):**

- Sets **`usage["input_tokens"]`** from raw **`input_tokens`**.
- Sets **`usage["cached_input_tokens"]`** from **`cache_read_input_tokens`**.
- Sets **`usage["cache_write_tokens"]`** from **`cache_creation_input_tokens`**.
- If **both** `input_tokens` and `cache_read_input_tokens` are present → **`usage_dimension_ambiguous:claude_cache_read_vs_gross_input`** (cannot disambiguate gross vs net input without provider contract clarification).

**Priced today:** only dimensions with non-null rates in the resolved catalog entry; **`cache_write_tokens`** is **never priced** in `_BILLABLE_DIMENSIONS` (`mode: "unpriced"`).

### 3.2 Gemini

**Capture:** `_extract_usage` maps SDK `usage_metadata` / `usageMetadata` to snake_case keys listed in `gemini_client.py` (including **`thoughts_token_count`**, **`cached_content_token_count`**).

**Normalization (`_apply_gemini_input_and_ambiguity_notes`):**

- If **`prompt_token_count`** and **`cached_content_token_count`** both set → **`input_tokens = prompt - cached`**, **`cached_input_tokens = cached`**.
- If only **`prompt_token_count`** → **`input_tokens = prompt`** and if prompt > 0 → **`usage_dimension_ambiguous:cached_input`** (cache may be embedded in prompt count).
- If **`candidates_token_count`** and **`thoughts_token_count`** both > 0 → **`usage_dimension_ambiguous:output_tokens`** (output vs “thinking” split ambiguous for billing).

**Thinking tokens:** mapped in **`normalize_usage`** into **`thinking_tokens`** from **`thoughts_token_count`**. Pricing requires **`thinking_cost_per_million`** on the catalog entry; embedded defaults for Gemini/OpenAI in the small embedded set may omit it.

### 3.3 OpenAI

**Capture:** `_openai_completion_usage_dict` dumps Chat Completions **`usage`** object (top-level + nested details dicts when `model_dump` returns dicts).

**Normalization (`_apply_openai_input_and_cache_conventions`):**

- If **`prompt_tokens`** and **`cached_input_tokens`** (already filled from `cached_tokens` / details) → **`input_tokens = prompt - cached`**.
- If only **`prompt_tokens`** → **`input_tokens = prompt`** and may add **`usage_dimension_ambiguous:cached_input`**.

**Responses API vs Chat:** adapter is built around **`completion`** with **`usage`**; there is no separate “Responses-only” usage extractor in the audited path — if the SDK returns a different shape, **`usage`** could be `{}` → downstream **`provider_usage_missing`**.

---

## 4. Pricing catalog and model alias audit

### 4.1 Sources

| Source | Location | Behavior |
|--------|----------|----------|
| Embedded defaults | `_EMBEDDED_DEFAULT_LLM_PRICING_CATALOG` in `costing.py` | **Two entries only:** `openai`/`gpt-5.4`, `claude`/`claude-sonnet-4-20250514` with input/output/cached_input rates. |
| Operator JSON | `Settings.llm_pricing_catalog_json` ← env **`LLM_PRICING_CATALOG_JSON`** | Parsed JSON; **`entries`** merged **by `(provider, model)` key**; **user entry overrides** embedded on same key. |
| Version label | `llm_pricing_catalog_version` / `LLM_PRICING_CATALOG_VERSION` | Stored into **`pricing_snapshot.pricing_version`** when set. |

### 4.2 Resolution rules

- **`_resolve_pricing_entry`:** iterate entries with matching **`provider`**; prefer **`model`** exact match (lowercased); else first **`model` in (`*`, `""`)** wildcard for that provider.
- **No aliases:** `claude-opus-4-7` ≠ `claude-sonnet-4-20250514` → **no row** unless catalog adds it.

### 4.3 Billing dimensions in catalog entries

Expected numeric rate keys (see `_build_pricing_snapshot_mutable` / `_BILLABLE_DIMENSIONS`):  
`input_cost_per_million`, `output_cost_per_million`, `cached_input_cost_per_million`, `thinking_cost_per_million`, `tool_request_unit_cost`, `image_input_unit_cost`, `audio_input_cost_per_million`, `video_input_cost_per_million`.  
Missing key → **`billable_dimension_not_priced:<dimension>`** when usage for that dimension > 0.

### 4.4 Example coverage table (codebase state)

| Provider | Example app model | Catalog key (embedded) | Alias? | Input / output / cached rates in embedded? | Status |
|----------|-------------------|-------------------------|--------|-----------------------------------------------|--------|
| Claude | `claude-opus-4-7` (from job) | Only `claude-sonnet-4-20250514` | **No** | N/A for opus | **Missing entry** → `pricing_entry_missing` |
| Claude | `claude-sonnet-4-20250514` | Same | N/A | Yes (embedded) | Can price if usage unambiguous |
| OpenAI | `gpt-4o` (common default) | Embedded has **`gpt-5.4`** only | **No** | N/A for 4o | **Likely missing** unless env catalog adds `gpt-4o` |
| Gemini | `gemini-2.5-pro` / `gemini-2.0-flash-exp` | **None** in embedded | **No** | N/A | **Missing** unless env catalog adds |

---

## 5. Active configured models vs pricing coverage

**Settings defaults (representative):**

- `GEMINI_MODEL_NAME` default `gemini-2.0-flash-exp` (`grouped_settings.py`).
- `OPENAI_MODEL` default `gpt-4o`.
- `PROCESSING_OPENAI_MODELS` default list includes **`gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`**.
- `PROCESSING_CLAUDE_MODELS` default **`claude-sonnet-4-20250514`, `claude-3-5-sonnet-20241022`** — **not** `claude-opus-4-7`.
- `processing_experiment_catalog` / `pipeline/providers/definitions.py` fallbacks: e.g. Claude **`claude-sonnet-4-20250514`**.

**Conclusion:** The **UI and env can advertise many models** (`PROCESSING_*_MODELS`, admin options), but **pricing coverage is only whatever is in merged catalog**. There is **no automatic sync** between “model offered for processing” and “model has a pricing row.”

---

## 6. Warning analysis

| Note / reason | Emitted where | Trigger | Correct? | Mitigation (H7) |
|---------------|---------------|---------|----------|-----------------|
| `pricing_entry_missing` | `build_llm_cost_snapshot` when `entry` is not a `dict` | No catalog row for `(provider, model)` | **Yes** for unknown models | Add catalog entries or aliases |
| `billable_dimension_not_priced:X` | `_apply_billable_dimensions_to_subtotals` | Usage > 0 for dimension but **`pricing_snapshot`** has **`null`** rate for that key | **Yes** | Extend catalog rates; for `cache_write_tokens` decide product rule (price vs exclude from notes) |
| `usage_dimension_ambiguous:claude_cache_read_vs_gross_input` | `_apply_claude_cache_conventions` | Both `input_tokens` and `cache_read_input_tokens` | **Conservative / intentional** | Provider-specific doc or dual-field interpretation from Anthropic docs |
| `usage_dimension_ambiguous:cached_input` | OpenAI / Gemini paths | Cannot split cached vs non-cached confidently | **Intentional** | Better raw field mapping per API version |
| `usage_dimension_ambiguous:output_tokens` | Gemini | Both candidates and thoughts > 0 | **Intentional** | Split billing rule for “thinking” vs output |
| `provider_usage_missing` | `build_llm_cost_snapshot` | No usage metadata keys present | Correct when empty | Fix adapter extraction |

**`total_cost_unavailable_reason` priority** (`_total_cost_unavailable_reason`): among others, **`pricing_entry_missing`** wins over **`billable_dimension_not_priced`** when both appear — UI may show **pricing_entry_missing** as headline even when dimension notes exist.

---

## 7. Claude findings

1. **`claude-opus-4-7`** can be an active model if set via **`claude_model_name`** in job metadata or **`anthropic_model`** / env — **not** required to be in `PROCESSING_CLAUDE_MODELS` for the HTTP call itself.
2. **Embedded catalog does not** include **`claude-opus-4-7`** → **`_resolve_pricing_entry` → `None`** → **`pricing_entry_missing`**.
3. **No alias resolver** in `costing.py` — similar Opus IDs under other strings are **not** merged.
4. **Cache ambiguity note** is emitted when **Anthropic returns both** gross-style **`input_tokens`** and **`cache_read_input_tokens`** — not “all Claude jobs”; it is **data-dependent**.
5. **Raw response** typically contains enough token counts to *estimate* cost **if** official per-million rates existed for that model and ambiguity were resolved or accepted.
6. **Non-implemented fix (H7):** add catalog row(s) for Opus (and other SKUs), and/or **alias table** `claude-opus-4-7` → canonical priced id; optionally adjust Claude convention to align with Anthropic’s documented meaning of `input_tokens` vs cache fields.

---

## 8. Gemini findings

1. **Fields captured:** see `GeminiClient._extract_usage` — prompt, candidates, total, thoughts, cached content.
2. **Separation:** normalization tries to separate prompt vs cached; **thinking** vs **candidates** triggers **output ambiguity** when both present.
3. **Embedded catalog:** **no Gemini entry** — all Gemini jobs depend on **`LLM_PRICING_CATALOG_JSON`** or accept missing costs.
4. **Double-counting risk:** when prompt and cached both present, code uses **`input_tokens = prompt - cached`** — **intended** to avoid double-counting **if** `prompt_token_count` is gross including cached.
5. **Thinking tokens:** captured into **`thinking_tokens`**; priced only if **`thinking_cost_per_million`** exists on the entry.
6. **H7:** add Gemini rows; define policy for thoughts vs candidates; extend tests with real `usage_metadata` shapes.

---

## 9. OpenAI findings

1. **API shape:** **`chat.completions.create`** path with **`completion.usage`** (`openai_sdk_adapter.py`).
2. **Fields:** `prompt_tokens`, `completion_tokens`, `total_tokens`, nested cached/reasoning in details when SDK exposes them.
3. **Cached input:** via **`prompt_tokens_details.cached_tokens`** or `input_tokens_details` path in **`normalize_usage`**.
4. **Reasoning tokens:** mapped to **`thinking_tokens`** from **`completion_tokens_details.reasoning_tokens`** (or `output_tokens_details`).
5. **Catalog:** embedded default is **`gpt-5.4`**, not **`gpt-4o`** — common deployments will hit **`pricing_entry_missing`** or missing rates unless env catalog is populated.
6. **H7:** align **`PROCESSING_OPENAI_MODELS`** with catalog keys; add **`gpt-4o`** / **`gpt-4o-mini`** rows; validate nested `model_dump` shapes for current OpenAI SDK.

---

## 10. Frontend auditability display findings

- **`JobAuditabilityPanel`** shows **`cost_snapshot`** fields; **`No informado`** comes from **`formatAuditCostFromApiString`** / missing token formatters when values are **`null`**.
- **`Tipo de cálculo: Estimado`** maps to **`capture_status === 'estimated'`** from backend — **not** a UI bug when costs are missing.
- **No evidence** the frontend strips `subtotal_*` or `capture_notes`; it surfaces **`total_cost_unavailable_reason`** and notes.

---

## 11. Root causes (consolidated)

1. **Catalog coverage gap** — embedded defaults cover **two** models; real jobs use **many** model strings.
2. **No alias / canonicalization** — `(provider, model)` must match catalog exactly.
3. **Conservative ambiguity notes** — especially Claude cache + Gemini output/thinking — force **`capture_status != exact`** and often **`total_cost` null** when combined with missing rates.
4. **`cache_write_tokens` always unpriced** — produces **`billable_dimension_not_priced:cache_write_tokens`** whenever write cache usage > 0 (may be noisy).
5. **Operational vs pricing config drift** — `PROCESSING_*_MODELS` / defaults are **not** validated against catalog at startup.

---

## 12. Recommended implementation plan for H7 (preview only)

1. **Versioned pricing catalog expansion** — ensure every **default processing model** has a row (Gemini, OpenAI, Claude SKUs in use).
2. **`model_alias` map** (config or catalog section) — map `claude-opus-4-7` → canonical priced key without duplicating rate rows (optional).
3. **Provider-specific usage normalizers** — tighten OpenAI Responses vs Chat if both exist; clarify Claude `input_tokens` vs cache read using vendor docs.
4. **Partial totals policy** — decide whether to show **partial `subtotal_*`** when `total_cost` is null (today UI can show all “No informado” for money while tokens exist).
5. **`cache_write` pricing or exclusion** — either add **`cache_write_cost_per_million`** (catalog + `_BILLABLE_DIMENSIONS`) or stop emitting **`billable_dimension_not_priced`** for that dimension if product accepts “free.”
6. **Tests** — golden `raw_usage` fixtures per provider + catalog variants (`test_llm_costing.py` patterns).
7. **Keep** Observability Auditabilidad as **read-only consumer** of persisted snapshot.

---

## 13. Risks and limitations

- **Official list prices** are a **product/finance** responsibility — code audit cannot validate dollar amounts.
- **Without DB access** this audit did **not** run aggregate statistics on production `result_json`. An optional read-only script such as `backend/scripts/audit_llm_cost_snapshots.py` (SELECT-only) could summarize `result_json` health; it should **no-op gracefully** when no DB is configured (document that limitation in the script docstring).
- **SDK version drift** may change `model_dump` keys — adapters should be regression-tested when upgrading `openai` / `anthropic` / `google-genai`.
- **Layering:** `llm_cost_snapshot_public_dict` (`backend/src/application/services/llm_cost_snapshot_public.py`) imports **`LlmCostSnapshotResponse`** from **`api.schemas`**. That couples **application** to **api**; a future refactor could move the shared DTO to a neutral contract module (non-blocking for H7 pricing work).

---

## 14. Final status

**`H6_AUDIT_READY_FOR_H7_IMPLEMENTATION`**

Root causes are clear in code: **pricing catalog / model key mismatch**, **no aliases**, **intentional ambiguity downgrades**, and **unpriced cache-write dimension**. Frontend faithfully displays backend state. H7 can proceed with catalog expansion, alias resolution, provider-specific normalization hardening, and characterization tests without blocking on undocumented runtime behavior.
