# E3 — EffectivePromptComposer

**Date:** 2026-05-11  
**Roadmap:** Phase E — Prompt Composer + Pipeline Integration

---

## 1. Executive summary

E3 adds a **pure, deterministic** `EffectivePromptComposer` in `backend/src/pipeline/services/effective_prompt_composer.py`. It consumes a caller-supplied protected hybrid base string, optional `SupplierPromptResolution` (E2), and lightweight reference metadata, and returns `EffectivePromptComposition` including **SHA256** of the final UTF-8 text and **E1** protected contract key/version echoes. Supplier text is appended only as a **fixed, delimited subordinate block** after the protected body; it is never merged into profile literals and never replaces the contract.

**No** production pipeline wiring, **no** LLM calls, **no** adapter, parser, normalizer, or schema changes.

---

## 2. Composer responsibilities

- Accept `EffectivePromptComposerInput` (no repositories).
- Preserve `protected_prompt_text` as the leading contract block.
- Apply supplier `editable_instructions` only when `resolution_status == "resolved"` and trimmed text is non-empty.
- For `fallback` and missing resolution: effective text equals protected base; copy fallback flags for audit.
- For `error`: effective text equals protected base; **do not** apply supplier text; set `fallback_used=True` and append resolution-error warnings (E4 may stop or branch).
- Compute `effective_prompt_hash = SHA256(effective_prompt_text, UTF-8)`.
- Echo `PROTECTED_PROMPT_CONTRACT_KEY` / `PROTECTED_PROMPT_CONTRACT_VERSION` from `protected_prompt_contract.py`.

---

## 3. Input shape

`EffectivePromptComposerInput` (frozen):

- `protected_prompt_text: str`
- `provider_name: str | None`, `model_name: str | None`
- `supplier_resolution: SupplierPromptResolution | None`
- `inventory_id`, `aisle_id`, `reference_source` (optional metadata; **not** hashed into prompt text)
- `reference_image_ids: tuple[str, ...]`

---

## 4. Output shape

`EffectivePromptComposition` (frozen): `effective_prompt_text`, `effective_prompt_hash`, protected contract key/version, provider/model echo from input, supplier config id/version when applicable, `supplier_instructions_applied`, `fallback_used`, `fallback_reason`, `reference_source`, `reference_image_ids`, `sections`, `warnings`.

---

## 5. Composition rules

| Resolution | Effective text | `supplier_instructions_applied` | `fallback_used` |
|------------|----------------|----------------------------------|-----------------|
| `None` | protected only | `False` | `False` |
| `fallback` | protected only | `False` | `True` (reason from resolution) |
| `error` | protected only | `False` | `True` |
| `resolved`, empty instructions | protected only | `False` | `False` + `EMPTY_SUPPLIER_INSTRUCTIONS` warning |
| `resolved`, non-empty | protected + delimiter block | `True` | `False` |

---

## 6. Supplier instruction boundary

Block headers:

- `--- SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS ---`
- Intro paragraph(s) stating subordination to JSON/schema/parser/provider rules.
- Raw trimmed supplier text (internal newlines preserved).
- `--- END SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS ---`

Supplier content is **not** interpreted as system instructions; it cannot replace the protected block (ordering: protected first).

---

## 7. Hashing strategy

- `hashlib.sha256(text.encode("utf-8")).hexdigest()`
- Hash covers **only** `effective_prompt_text` (no timestamps, no extra metadata in the digest).

This is **separate** from existing `prompt_hash` / `base_prompt_hash` in other modules (E3 does not replace them).

---

## 8. Behavior for resolved / fallback / error

- **Fallback:** no extra text to the model; metadata carries `fallback_reason` for operators/audit.
- **Error:** no supplier application; warnings include `RESOLUTION_STATUS_ERROR` and `RESOLUTION_ERROR_CODE:{code}` when present; merges any `resolution.warnings` from E2.
- **Resolved:** trim-only normalization on instructions; whitespace-only → same as empty case with config id/version retained.

---

## 9. Files changed

| File | Role |
|------|------|
| `backend/src/pipeline/services/effective_prompt_composer.py` | Composer + input/output dataclasses + `compute_effective_prompt_hash` |
| `backend/tests/pipeline/test_effective_prompt_composer.py` | Unit + optional `compose_hybrid_base` marker test |
| `audit/phase-e/e3-effective-prompt-composer.md` | This document |
| `audit/phase-e/e3-closure.md` | Closure |

---

## 10. Tests added

See test module: no resolution, fallback, resolved append, malicious supplier text ordering, empty whitespace, error path, hash stability, contract metadata, UTF-8 hash helper, hybrid base + supplier preserves E1 shared markers.

---

## 11. Runtime behavior impact

**None** in production: composer is not imported by job executor or hybrid pipeline for live `LLMRequest` assembly in this phase.

---

## 12. Remaining risks

- **Max length:** no hard cap on supplier instructions in E3; long text increases tokens — consider a product limit in a later phase if D2 does not define one.
- **E4 wiring:** must keep adapter JSON suffixes **after** this composed body where applicable (composer does not add OpenAI JSON suffixes).

---

## 13. E3 final status recommendation

`PHASE_E3_CLOSED_READY_FOR_E4`
