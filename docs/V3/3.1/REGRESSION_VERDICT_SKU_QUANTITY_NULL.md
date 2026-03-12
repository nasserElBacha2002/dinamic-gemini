# Regression Verdict: SKU / internal_code and quantity null (current branch vs main)

## 1. Investigation verdict

**Regression type: prompt-side.**

On **main**, Gemini receives the **base prompt only** (`get_hybrid_prompt()`). The model returns `internal_code` and `product_label_quantity` when it can read them from labels.

On the **current branch** (pre-fix), the effective prompt sent to Gemini was **base + Epic 3.1.D product/label association block** (and for photos jobs also image IDs + traceability). The Epic D block states:

- *"use internal_code ONLY for the product/SKU code from the product label"*
- *"Use position_barcode ONLY for the position or pallet barcode/label"*

That wording made Gemini **overly conservative**: it began returning `internal_code: null` and `product_label_quantity: null` for entities (including when position barcodes were present), as seen in `output/.../run/gemini_raw_response.json`. So the regression is **not** in parsing, domain shaping, or API flattening — **Gemini stopped populating those fields** under the new prompt.

- **Parser:** Unchanged for `internal_code` and `product_label_quantity`; both branches use `_safe_str(e.get("internal_code"))` and `_safe_int(e.get("product_label_quantity"))`.
- **Mapping / report / positions:** No code path overwrites or drops these fields; they are copied from parsed entities into `detected_summary_json` and then used by the list API. The nulls were already present in the raw Gemini response.

---

## 2. Exact failing code path

| Layer | File | Responsibility |
|-------|------|----------------|
| **Prompt construction** | `src/pipeline/adapters/gemini_analysis_provider.py` | Built `prompt_text = get_hybrid_prompt()` then **appended** `enrich_prompt_with_product_label_association(prompt_text)`, so the sent prompt included the Epic D block. |
| **Prompt fallback** | `src/llm/providers/gemini_provider.py` | When `request.prompt` was empty, used `enrich_prompt_with_product_label_association(get_hybrid_prompt(...))`, so fallback also added the Epic D block. |
| **Analyzer fallback** | `src/llm/gemini_global_analyzer.py` | When `_prompt_text` was None, used `enrich_prompt_with_product_label_association(get_hybrid_prompt())`, again adding the Epic D block. |
| **Observed effect** | `output/<job_id>/run/gemini_raw_response.json` | Every entity had `internal_code: null` and `product_label_quantity: null`; downstream layers correctly preserved these values, so positions/entities showed null. |

The **root cause** is the **addition of the Epic 3.1.D product/label association block** to the prompt, which changed model behavior so that SKU and quantity are no longer filled when the model is uncertain, instead of being filled from visible labels as on main.

---

## 3. What changed relative to main

- **main:** Adapter set `request.prompt = get_hybrid_prompt()` (base only). Provider used that prompt. No product/label block, no image-ID/traceability block in the default path.
- **current (pre-fix):** Adapter set `prompt_text = get_hybrid_prompt()` then `prompt_text = enrich_prompt_with_product_label_association(prompt_text)`, and for photos also `enrich_prompt_with_image_ids(prompt_text, images)`. Provider used `request.prompt` when non-empty; fallback used `enrich_prompt_with_product_label_association(get_hybrid_prompt(...))`. So the **effective prompt** always included the Epic D block, and for photos also the image list + traceability instruction.

The only change that degrades SKU/quantity extraction is the **product/label association block** (`_PRODUCT_LABEL_ASSOCIATION` in `src/llm/prompts.py`). Image IDs + traceability do not remove or override instructions for `internal_code` or `product_label_quantity`; they add extra constraints. The minimal fix is to stop appending the product/label block so the prompt matches main for core extraction.

---

## 4. Minimal fix applied

1. **Adapter** (`src/pipeline/adapters/gemini_analysis_provider.py`): Stop calling `enrich_prompt_with_product_label_association(prompt_text)`. Use base prompt only; for photos jobs keep `enrich_prompt_with_image_ids(prompt_text, images)` so traceability (e.g. `source_image_id`) is still requested.
2. **Provider** (`src/llm/providers/gemini_provider.py`): When `request.prompt` is empty, use `get_hybrid_prompt(...)` only (no `enrich_prompt_with_product_label_association`).
3. **Analyzer** (`src/llm/gemini_global_analyzer.py`): When `_prompt_text` is None, use `get_hybrid_prompt()` only (no Epic D block).

**Effect:** Gemini again receives the same base prompt as on main (plus, for photos, image list + traceability). SKU and quantity should be populated when the model can read them, restoring main behavior. Epic 3.1.D clarification can be revisited later with softer wording (e.g. “prefer internal_code for product/SKU and position_barcode for position/pallet”) if we want to keep the distinction without inducing nulls.

---

## 5. Optional hardening

- **Prompt snapshot test:** Snapshot the effective prompt string (base vs base+Epic D) so changes to prompt composition are detected.
- **Parser fixture test:** Feed a JSON with non-null `internal_code` and `product_label_quantity` and assert they appear in parsed entities and in `detected_summary_json`.
- **Golden run:** For a fixed input, compare `gemini_raw_response.json` (or at least entity fields) between a run on main and current after fix to confirm entity-level SKU/quantity are again populated when visible in the image.
- **Regression test:** Add a test that, for a mocked Gemini response containing non-null `internal_code` and `product_label_quantity`, the positions list (or entities) expose them (e.g. `sku` / `detected_quantity` or equivalent) and do not overwrite with null.
