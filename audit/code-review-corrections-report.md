# Code review corrections report — OpenAI model_entity_id + traceability hardening

## 1. Executive summary

- **Status:** READY_FOR_MERGE
- **Files changed:** 9 (tests, normalization helper, OpenAI adapter, restored audit report)
- **Tests run:** Focused suite (see §7) — all passed; `ruff check` passed
- **Final verdict:** Cleanup complete; production Gemini path uses `request.frame_refs` from pipeline; video/photo sources emit stable non-empty refs

## 2. Corrections applied

| Review item | Action taken | Files |
|-------------|--------------|-------|
| C1 — duplicate import | Removed duplicate line | `test_phase1_image_traceability.py` |
| C2 — `analyze_video_frames` call sites | Audited 8 call sites; fixed 3 tests missing `frame_refs` | `test_gemini_global_analyzer_json_root.py`, `test_stage_2_1_a.py`, `test_stage2_single_call_hybrid.py` |
| C3 — video/legacy frames | Confirmed `VideoFrameSource` → `frame_{idx:06d}`; `FrameAcquisitionStage` keeps len alignment; strict validation kept for all jobs | `test_phase1_image_traceability.py` (new regression) |
| C4 — audit report retention | Restored `phase1-image-traceability-fix-report.md` from git; kept hardening report | `audit/` |
| C5 — OpenAI repair indexes | `ModelEntityIdRepairDiagnostic` with `.index`; log uses structured indexes | `model_entity_id.py`, `openai_sdk_adapter.py` |

## 3. analyze_video_frames call-site audit

**Command:** `rg "analyze_video_frames\\(" backend/src backend/tests`

| Location | Type | frame_refs |
|----------|------|------------|
| `gemini_sdk_adapter.py` | Production | `list(request.frame_refs)` from hybrid pipeline |
| `gemini_global_analyzer.py` | Definition | Required when building labeled payloads |
| `test_stage3_validation.py` | Test | `["img_001"]` ✓ |
| `test_gemini_interleaved_adapter.py` | Test | `["img_010"]` ✓ |
| `test_gemini_global_analyzer_json_root.py` | Test | **Fixed** → `["frame_0"]` |
| `test_stage_2_1_a.py` | Test | **Fixed** → `["frame_0"]` |
| `test_stage2_single_call_hybrid.py` | Test | **Fixed** → `["frame_0"]` |

**Production:** Only `gemini_sdk_adapter` calls `analyze_video_frames`; it always passes `frame_refs` from `LLMRequest`, populated by `HybridGlobalAnalysisStrategy` from `AcquiredFrames.frame_refs`.

## 4. Video / legacy frame behavior

- **Non-photo jobs:** Still active (`input_type=video` via `VideoFrameSource`).
- **Refs:** `video_source.py` assigns `frame_{idx:06d}` for every extracted frame.
- **Acquisition:** `FrameAcquisitionStage` appends one ref per loaded frame; fallback `frame_{i}` if bundle ref missing.
- **Strict validation:** Applies to all jobs with `frames_nd` (photos and video). Safe because sources guarantee non-empty aligned refs.
- **Traceability:** Photo jobs use manifest `image_id`; video uses technical frame refs (not manifest UUIDs) — entity `source_image_id` validation for photos uses sent-frame allowlist only when `input_type=photos`.

## 5. Audit report retention decision

**Restored** `audit/phase1-image-traceability-fix-report.md` from commit `95f5cf5`.

**Kept** `audit/phase1-image-traceability-hardening-report.md` and `audit/openai-model-entity-id-schema-tolerance-report.md`.

Historical Phase 1 fix report is not superseded; hardening is documented separately.

## 6. OpenAI model_entity_id repair

Structured `ModelEntityIdRepairDiagnostic` (`kind`, `index`, `generated_id`, `message`).

`LLMResponse.usage["model_entity_id_repair_warnings"]` remains a **list of strings** (backward compatible).

Logging uses `d.index` directly (no string parsing).

## 7. Tests

```bash
cd backend && python3 -m pytest \
  tests/llm/test_model_entity_id_normalization.py \
  tests/llm/test_openai_sdk_adapter.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/pipeline/test_phase1_image_traceability.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/llm/test_gemini_interleaved_adapter.py \
  tests/llm/test_anthropic_labeled_content.py \
  tests/llm/test_deepseek_sdk_adapter.py \
  tests/pipeline/test_hybrid_analysis_prompt_service.py \
  tests/pipeline/test_prompt_composition_propagation.py \
  tests/test_stage3_validation.py \
  tests/llm/test_gemini_global_analyzer_json_root.py \
  -q

cd backend && python3 -m ruff check src tests
```

**Results:** 80 passed; ruff clean.

## 8. Remaining risks

- Model may still choose the wrong **valid** sent frame among similar views.
- `frames_sent_ids` are not persisted in DB (execution log / prompt composition only).
- UI may still interpret `valid` as visually confirmed (future phase).
- GPT may fail on other required schema fields besides `model_entity_id`.

## 9. Final status

**READY_FOR_MERGE**
