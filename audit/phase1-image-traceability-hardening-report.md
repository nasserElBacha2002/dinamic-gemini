# Phase 1 follow-up image traceability hardening report

## 1. Executive summary

- **Status:** READY_FOR_MERGE
- **Files changed:** 12 production modules + 8 test files + this report
- **Tests added/updated:** Enrichment partial-ID cases, frame-ref validation, integration propagation, Gemini/Claude adapter tests; OpenAI/DeepSeek/Gemini stage tests aligned with frame-ref guard
- **Behavior changed:** Prompt lists every sent ID (including IDs missing from manifest metadata); primary frames without matching non-empty refs fail before provider calls; prepared execution log no longer shows empty `multimodal_order`

## 2. Corrections applied

| Review finding | Fix | Files |
|----------------|-----|-------|
| C1 — partial sent IDs dropped from prompt | `enrich_prompt_with_sent_image_ids` iterates all `sent_image_ids` in order; ID-only line when no `JobImage` | `enrichments.py`, tests |
| C2 — unlabeled primary when refs mismatch | `validate_primary_frame_refs()`; called in builders + `HybridGlobalAnalysisStrategy` | `vision_multimodal_payload.py`, `hybrid_global_analysis_strategy.py` |
| C3 — no end-to-end propagation test | `test_phase1_sent_frame_propagation.py` | new test |
| C4 — Gemini/Claude adapter coverage | `test_gemini_interleaved_adapter.py`, `test_anthropic_labeled_content.py` | new tests |
| C5 — stale VALID enum comment | Docstrings/comments updated | `traceability.py` |
| C6 — misleading prepared log | `multimodal_order_status: pending_adapter_materialization` on prepared; full order on finished | `hybrid_global_analysis_strategy.py` |

## 3. Prompt / sent-frame consistency

- `HybridGlobalAnalysisStrategy` passes `sent_frame_refs=frame_refs` (full list, validated).
- `prompt_listed_image_ids` and `frames_sent_ids` are both `list(frame_refs)`.
- `enrich_prompt_with_sent_image_ids` renders **every** sent ID in that order (metadata line or `- {id}`).
- Provider labels use `frame_refs[i]` after validation (non-empty).
- `EntityResolutionStage` validates against `prompt_composition.frames_sent_ids`.

## 4. Provider payload safety

- `len(primary_frames_nd) != len(frame_refs)` → `ValueError` with `PRIMARY_FRAME_REFS_MISMATCH`.
- Empty/whitespace `frame_refs` → same error with `empty_ref_indices`.
- Reference images without IDs → `reference_id: unknown`, `REFERENCE_ONLY` (no validation on refs).

## 5. Logging behavior

| Event | Fields |
|-------|--------|
| **prepared** | `frames_sent_ids`, `prompt_listed_image_ids`, `reference_image_ids`, `multimodal_order_status: pending_adapter_materialization` |
| **finished** | `multimodal_order`, `frames_sent_ids` (when populated by adapter) |

## 6. Tests

```bash
cd backend && python3 -m pytest \
  tests/llm/test_vision_multimodal_payload.py \
  tests/pipeline/test_phase1_image_traceability.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/llm/test_openai_sdk_adapter.py \
  tests/llm/test_gemini_interleaved_adapter.py \
  tests/llm/test_anthropic_labeled_content.py \
  tests/llm/test_deepseek_sdk_adapter.py \
  tests/pipeline/test_hybrid_analysis_prompt_service.py \
  tests/pipeline/test_prompt_composition_propagation.py \
  tests/test_stage3_validation.py \
  -q
```

**Result:** 72 passed.

## 7. Remaining risks

- Model may still pick the wrong image among **valid** sent frames.
- `frames_sent_ids` are not persisted in DB (execution log / prompt composition only).
- UI may still treat `valid` as visually confirmed (future Phase 2).

## 8. Final status

**READY_FOR_MERGE**
