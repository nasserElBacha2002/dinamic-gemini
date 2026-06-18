# Phase 4.4 — Execution Log Artifact Hotfix

## 1. Executive summary

**Verdict:** HOTFIX_VALIDATED

| Item | Status |
|------|--------|
| Gemini analysis preserved | Yes (prior hotfix retained) |
| Canonical Phase 4.4 provider path | Yes |
| Runtime objects excluded from serializable metadata | Yes |
| execution_log JSONL safe for artifact staging | Yes |
| Phase 4.5 started | No |
| Video traceability implemented | No |

## 2. Root cause

After Phase 4.4, provider execution introduced runtime image objects (NumPy arrays, PIL images, `google.genai.types.Part`, provider request/payload objects). While `LLMRequest` gained runtime-only fields, metadata and execution_log payloads could still carry non-JSON-serializable values when:

- analysis metadata was logged to `execution_log.jsonl` without redacting runtime leaks;
- `prompt_composition` / provider metadata was propagated to `run_metadata` without sanitization;
- artifact staging uploaded `execution_log.jsonl` that contained invalid JSON lines.

Artifact publication then failed permanently for kind `execution_log` even when pipeline analysis and DB persist succeeded.

## 3. Failing artifact kind / path

| Field | Value |
|-------|-------|
| Artifact kind | `execution_log` |
| Typical failing path | `payload._serialized_multimodal_payload` or nested `encoded_resource` / ndarray |
| Python types | `ndarray`, `PIL.Image`, `types.Part`, `ProviderExecutionRequest`, `SerializedMultimodalPayload` |

## 4. Affected files

| File | Change |
|------|--------|
| `backend/src/pipeline/execution_log_sanitizer.py` | New — `make_json_safe_for_execution_log()` |
| `backend/src/pipeline/llm_metadata_json_safety.py` | New — `sanitize_llm_metadata()` |
| `backend/src/pipeline/execution_log.py` | Stronger sanitization + failing path logging + `validate_execution_log_jsonl_file()` |
| `backend/src/pipeline/run_metadata.py` | Sanitize `prompt_composition` before persist |
| `backend/src/pipeline/adapters/hybrid_global_analysis_strategy.py` | `sanitize_llm_metadata(req_meta)` before `LLMRequest` |
| `backend/src/application/services/artifact_publication_dispatcher.py` | Validate execution_log JSONL before staging |
| Tests | `test_execution_log_json_safety.py`, `test_execution_log_artifact_publication.py`, updated metadata tests |

## 5. Runtime vs serializable metadata boundary

**Runtime-only (never in metadata / logs / artifacts):**

- `LLMRequest.provider_execution_request`
- `LLMRequest.serialized_multimodal_payload`
- `LLMRequest.frames_nd`, `LLMRequest.context_images`

**Serializable metadata (JSON-safe projections only):**

- `provider_execution_request` snapshot (`to_dict()` without resources)
- `provider_image_manifest_order`, `multimodal_order`, `frames_sent_ids`
- `execution_image_manifest`, `prompt_image_projection`
- traceability / provider identity fields

**Strategy boundary:** `sanitize_llm_metadata()` runs on `req_meta` immediately before `LLMRequest` construction.

## 6. Sanitizer behavior

`make_json_safe_for_execution_log()`:

- primitives unchanged;
- `Path` → string; `Enum` → value; `datetime` → ISO string;
- `bytes` → `{__redacted_runtime_object__: "bytes", byte_length: N}`;
- `ndarray` → redacted placeholder with `shape` + `dtype`;
- `PIL.Image` → redacted placeholder with `mode` + `size`;
- `google.genai.types.Part` → redacted placeholder;
- provider runtime types → redacted placeholder;
- known runtime metadata keys (`_serialized_multimodal_payload`, etc.) → redacted;
- recursive dict/list/tuple walk with dotted `path` for diagnostics.

Execution log writer logs `execution_log serialization failed at <path>` when JSON encoding still fails.

## 7. Tests added

- `tests/pipeline/test_execution_log_json_safety.py` (8)
- `tests/pipeline/test_execution_log_artifact_publication.py` (1)
- Updated `tests/pipeline/test_provider_metadata_serialization.py`

## 8. Commands and results

```bash
cd backend && python3 -m pytest \
  tests/pipeline/test_execution_log_json_safety.py \
  tests/pipeline/test_execution_log_artifact_publication.py \
  tests/pipeline/test_provider_metadata_serialization.py \
  tests/test_execution_log.py \
  tests/llm/test_gemini_serialized_materialization.py \
  tests/pipeline/test_provider_payload_parity.py \
  tests/pipeline/test_provider_multimodal_cross_provider.py \
  tests/pipeline/test_provider_execution_integration.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  -q --no-cov
```

**Result:** 54 passed, 0 failed, 0 skipped

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q src
```

**Result:** success

## 9. Remaining risks

- Full-tree metadata audit on legacy code paths outside hybrid strategy not exhaustively proven;
- `sanitize_llm_metadata` redacts unknown objects rather than failing the pipeline (defensive by design);
- broader finalization-state semantics unchanged (artifact failure may still mark job failed per existing policy).

## 10. Confirmations

- **Phase 4.5 not started**
- **Video traceability not implemented**
