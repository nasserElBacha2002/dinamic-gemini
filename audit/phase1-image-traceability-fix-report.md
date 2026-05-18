# Phase 1 image traceability fix report

## 1. Executive summary

- **Status:** READY_FOR_REVIEW
- **Files changed:** 14 backend modules + 4 test files
- **Tests added/updated:** `test_vision_multimodal_payload.py`, `test_phase1_image_traceability.py`, `test_openai_sdk_adapter.py`; existing epic 3.1.B tests pass
- **Behavior changed:** Traceability validation uses **sent primary frame IDs** only; prompts list the same IDs; OpenAI/Claude/Gemini payloads interleave explicit labels before each image; execution logs include `frames_sent_ids`, `prompt_listed_image_ids`, `multimodal_order`

## 2. Root causes addressed

| Audit finding | Fix |
|---------------|-----|
| Validation against full manifest | `EntityResolutionStage` uses `prompt_composition.frames_sent_ids` (fallback: manifest when absent) |
| Prompt lists all manifest IDs | `build_hybrid_analysis_prompt_with_traceability(..., sent_frame_refs=frame_refs)` + `enrich_prompt_with_sent_image_ids` |
| Unlabeled vision parts | `vision_multimodal_payload.py` — `REFERENCE_ONLY` / `PRIMARY_EVIDENCE` text before each image |
| Gemini images-before-text | Gemini uses interleaved `contents`: main prompt text first, then label+image pairs |
| Supplier refs shift index | Reference images labeled; not in prompt ID list; not in `frames_sent_ids` |
| Weak invalid-ID diagnostics | `apply_traceability_validation(..., manifest_image_ids=...)` distinguishes manifest-only vs unknown IDs |
| Log observability gap | `multimodal_order`, `frames_sent_ids`, `prompt_listed_image_ids` on execution log + request metadata |

## 3. New traceability flow

1. **Sent frame IDs** — `FrameAcquisitionStage` caps frames; `frame_refs` on `AcquiredFrames` are copied to `LLMRequest` and `composition.frames_sent_ids`.
2. **Prompt-listed IDs** — Hybrid prompt enrichment lists only those IDs (same order as `frame_refs`).
3. **Provider image labels** — Adapters build interleaved text+image parts with `source_image_id` / `reference_id` and `role`.
4. **Model returns `source_image_id`** — Unchanged contract.
5. **Validation** — `valid_image_ids = frozenset(frames_sent_ids)`; manifest used only for warning text.
6. **Persisted status** — `valid` / `invalid` / `missing` / `unvalidated` in hybrid report as before.

## 4. Provider-specific changes

| Provider | Change | Risk reduced |
|----------|--------|--------------|
| **OpenAI** | Labeled interleaved `content[]`; `multimodal_order` in metadata | Index-only inference; unseen manifest IDs marked invalid |
| **Claude** | Same labeling pattern as OpenAI | Same |
| **Gemini** | `contents` = prompt text first + labeled pairs (not images-then-single-text) | Weak ID binding at end of payload |
| **DeepSeek** | No change — multimodal still blocked (`UNSUPPORTED_MULTIMODAL_PROVIDER`) | No false VALID on text-only runs |

## 5. Validation behavior

- **valid** — `source_image_id` in sent primary `frame_refs`
- **invalid** — ID present but not in sent set; warning mentions *not part of model input frames* when ID exists in manifest
- **missing** — null/empty `source_image_id`
- **unvalidated** — no validation context (empty sent set and no fallback)

## 6. Execution log improvements

Sample payload fields on `analysis_request` / `analysis_request finished`:

```json
{
  "frames_sent_ids": ["img_001", "img_002"],
  "prompt_listed_image_ids": ["img_001", "img_002"],
  "reference_image_ids": ["supplier-ref-1"],
  "multimodal_order": [
    {"index": 0, "role": "text", "kind": "main_prompt"},
    {"index": 1, "role": "text", "kind": "reference_image_label", "reference_id": "supplier-ref-1"},
    {"index": 2, "role": "image", "kind": "reference", "reference_id": "supplier-ref-1"},
    {"index": 3, "role": "text", "kind": "primary_image_label", "source_image_id": "img_001"},
    {"index": 4, "role": "image", "kind": "primary_evidence", "source_image_id": "img_001"}
  ]
}
```

`multimodal_order` is populated after the adapter builds the request (post-`execute` on finished event).

## 7. Tests

```bash
cd backend && python3 -m pytest \
  tests/llm/test_vision_multimodal_payload.py \
  tests/pipeline/test_phase1_image_traceability.py \
  tests/test_epic_3_1_b.py \
  tests/llm/test_openai_sdk_adapter.py \
  tests/llm/test_deepseek_sdk_adapter.py \
  tests/pipeline/test_hybrid_analysis_prompt_service.py \
  tests/pipeline/test_prompt_composition_propagation.py \
  -q
```

**Result:** 79 passed (local run subset).

## 8. Risks / follow-up

- Model may still pick the wrong **sent** image among similar views (`valid` ≠ visually correct).
- Frontend may need warnings when `traceability_status=valid` but UX should show frame-cap context (Phase 2).
- Consider persisting `frames_sent_ids` on job/run records for API consumers without execution logs.
- Unit tests that call `build_hybrid_analysis_prompt_with_traceability` without `sent_frame_refs` still use full-manifest enrichment (legacy test path).

## 9. Final status

**READY_FOR_REVIEW**
