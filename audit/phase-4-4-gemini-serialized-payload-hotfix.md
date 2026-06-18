# Phase 4.4 — Gemini Serialized Payload Hotfix

## 1. Executive summary

**Verdict:** HOTFIX_VALIDATED

| Item | Status |
|------|--------|
| Root cause identified | Yes |
| Canonical Phase 4.4 path preserved | Yes |
| Legacy photo downgrade avoided | Yes |
| Phase 4.5 started | No |
| Video traceability implemented | No |

## 2. Root cause

`build_gemini_contents_from_serialized()` appended `entry.encoded_resource` directly into Gemini `contents`.

For V3 photo jobs the serialized entries contain:

- **Primary evidence:** OpenCV BGR `numpy.ndarray`
- **Reference images:** `PIL.Image` (when present)

The Gemini SDK accepts PIL images in the legacy interleaved path, but raw ndarrays (and arbitrary objects) trigger SDK-side validation errors such as:

```text
file uri and mime_type are required
```

This surfaced as `generate_global_analysis_structured falló tras 3 intentos` and was mapped to `LLMProviderError` code `UNKNOWN` because the failure occurred inside the remote retry loop as a `RuntimeError`.

## 3. Affected files

| File | Change |
|------|--------|
| `backend/src/llm/vision_multimodal_payload.py` | Added `materialize_gemini_serialized_image()`; updated `build_gemini_contents_from_serialized()` |
| `backend/src/llm/gemini_global_analyzer.py` | Pass `job_id` into serialized builder |
| `backend/tests/llm/test_gemini_serialized_materialization.py` | New focused materialization + regression tests |
| `backend/tests/pipeline/test_provider_multimodal_cross_provider.py` | Reference fixture uses PIL instead of raw `object()` |

## 4. Exact fix

Introduced Gemini-specific materialization at the serialized payload boundary:

```text
SerializedImagePayloadEntry
→ materialize_gemini_serialized_image()
  - ndarray (BGR) → PIL RGB (same conversion as legacy `_ndarray_to_pil`)
  - PIL Image → pass-through
  - bytes + supported MIME → `types.Part.from_bytes(...)`
  - unsupported / missing MIME / unknown type → ProviderImageExecutionError (pre-remote)
→ build_gemini_contents_from_serialized()
→ Gemini API call
```

`ProviderImageExecutionError` continues to map to `LLMProviderError` with the specific code in `GeminiSdkAdapter` (not `UNKNOWN`).

## 5. Before vs after Gemini payload shape

### Before

```text
[prompt, label_REF_001, <raw ndarray|PIL|object>, label_IMG_001, <raw ndarray>, ...]
```

### After

```text
[prompt, label_REF_001, <PIL Image|Part with mime>, label_IMG_001, <PIL Image>, ...]
```

No raw `numpy.ndarray` or arbitrary wrappers are appended.

## 6. Tests added

`tests/llm/test_gemini_serialized_materialization.py` (9 tests):

- primary ndarray → PIL
- reference PIL → accepted
- bytes + MIME → `types.Part`
- bytes without MIME → `PROVIDER_IMAGE_SERIALIZATION_FAILED`
- unsupported MIME → `PROVIDER_IMAGE_UNSUPPORTED_FORMAT`
- unsupported resource type → `PROVIDER_IMAGE_SERIALIZATION_FAILED`
- order + manifest/source metadata preserved
- no raw ndarray in built contents
- **5-photo canonical job regression** through `resolve_serialized_payload_for_adapter` + `GeminiGlobalAnalyzer` mock

## 7. Commands run and results

```bash
cd backend && python3 -m pytest \
  tests/pipeline/test_provider_payload_parity.py \
  tests/pipeline/test_provider_multimodal_cross_provider.py \
  tests/pipeline/test_provider_execution_integration.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/llm/test_gemini_serialized_materialization.py \
  -q --no-cov
```

**Result:** 30 passed, 0 failed, 0 skipped

## 8. Remaining risks

- Image downsampling (`max_side`) still occurs in legacy paths; serialized path materializes full ndarray → PIL without additional resize (same as legacy interleaved path).
- Bytes-based serialized entries are supported but not used in current photo acquisition; behavior is tested defensively.
- DeepSeek / video legacy builders unchanged (out of scope).

## 9. Confirmations

- **Phase 4.5 not started**
- **Video traceability not implemented**
- **Canonical `ProviderExecutionRequest` path remains mandatory for photo V3 manifest jobs**
