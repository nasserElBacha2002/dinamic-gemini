# Epic 3.1.D — Backend Implementation Plan (prompt + product/label association)

**Scope:** Backend-only. Prompt improvements and product/label association for clearer review and audit. No frontend. No LLM call changes beyond prompt text.

**Source of truth:** `docs/V3/V3.0.md` (3.1.D: "mejoras del prompt y asociación producto/etiqueta"), `docs/V3/Documento tecnico - 3.0.md` (§17 lineamientos v3.1), `docs/V3/3.1/3.1 Documento tecnico.md`.

**Post-implementation corrections (hardening):** Field renamed to `review_display_label` (semantically clear: review-oriented, not guaranteed product-only). Prompt enrichment is explicit via `enrich_prompt_with_product_label_association()` at request-building layer; `get_hybrid_prompt()` returns base only. Derivation centralized in `src/reporting/display_label.py` (`derive_review_display_label`). API keeps `product_display_label` as backward-compat alias (same value as `review_display_label`).

---

## Interpreted scope of Epic D

- **Mejoras del prompt:** Add explicit instructions so the provider returns a clear separation between **product** identifier (internal_code = product/SKU from the product label) and **position/pallet** identifier (position_barcode = position or pallet barcode). Applied via explicit enrichment at pipeline/provider layer, not globally in get_hybrid_prompt.
- **Asociación producto/etiqueta:** Expose a single review/export display label per entity: `review_display_label` = internal_code else position_barcode (derived via centralized helper; None/empty/whitespace normalized). API also returns `product_display_label` as alias for backward compatibility.

## Out of scope (left for later)

- Frontend UI changes.
- Multi-evidence or primary_image_id.
- New LLM calls or schema changes to the provider response schema (only prompt text and backend-derived display field).
- Redesign of persistence or pipeline.

---

## Backend modules touched

| Module | Change |
|--------|--------|
| `src/reporting/display_label.py` | Centralized `derive_review_display_label(internal_code, position_barcode)`; normalizes None/empty/whitespace. |
| `src/llm/prompts.py` | Base prompt only in `get_hybrid_prompt()`; new `enrich_prompt_with_product_label_association(base_prompt)`; enrichment applied at call sites. |
| `src/pipeline/adapters/gemini_analysis_provider.py` | After `get_hybrid_prompt()`, call `enrich_prompt_with_product_label_association(prompt_text)`. |
| `src/llm/providers/gemini_provider.py` | Fallback path: use enriched prompt via helper. |
| `src/llm/gemini_global_analyzer.py` | Fallback path: use enriched prompt via helper. |
| `src/reporting/hybrid_report.py` | Per-entity `review_display_label` via `derive_review_display_label(e.internal_code, e.position_barcode)`. |
| `src/api/schemas/responses.py` | `review_display_label` (primary), `product_display_label` (deprecated alias). |
| `src/api/routes/entities.py` | Set both from `derive_review_display_label(...)`. |
| `src/reporting/artifacts.py` | CSV column `review_display_label`; value from helper. Docstring documents Epic D contract evolution. |
| `src/domain/entity.py` | Comments: internal_code = product/SKU only; position_barcode = position/pallet only. |
| `src/models/schemas.py` | Field descriptions aligned with Epic 3.1.D semantics. |
| `tests/test_epic_3_1_d.py` | Tests for helper, prompt enrichment, report/API/CSV with `review_display_label` and backward compat. |

---

## Implementation details

### 1. Prompt (prompts.py)

- `get_hybrid_prompt()` returns **base prompt only** (no Epic D block). This avoids silent global behavior change.
- New `enrich_prompt_with_product_label_association(base_prompt)` appends the product/label association block. Called explicitly in pipeline adapter and in provider/analyzer fallback paths.

### 2. Report (hybrid_report.py)

- Each entity dict includes `review_display_label`: `derive_review_display_label(e.internal_code, e.position_barcode)`. Empty and whitespace-only treated as missing.

### 3. API (responses.py, entities.py)

- `EntityListItem`: `review_display_label` (primary), `product_display_label` (alias, same value).
- `list_entities`: always derives via `derive_review_display_label(e.get("internal_code"), e.get("position_barcode"))`; sets both response fields.

### 4. Export (artifacts.py)

- CSV column `review_display_label`; value from `derive_review_display_label(...)`. Docstring documents additive Epic D contract.

### 5. Tests

- Helper: prefer internal_code, fallback position_barcode, None/empty/whitespace.
- Prompt: base from `get_hybrid_prompt()` does not contain association text; enriched prompt does; enrichment applied at intended call sites.
- Report/API/CSV: `review_display_label`; API also returns `product_display_label`; legacy report without key still gets derived value.

---

## Backward compatibility

- New fields optional. API returns both `review_display_label` and `product_display_label` (same value); old clients can keep using `product_display_label`.
- Report uses `review_display_label`; API derives from entity dict so legacy reports without the key still work.
- Prompt enrichment is additive and applied only where intended.
