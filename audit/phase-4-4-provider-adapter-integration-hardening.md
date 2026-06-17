# Phase 4.4 — Provider Adapter Integration Hardening

## 1. Executive summary

**Verdict:** COMPLETE_WITH_RISKS

| Question | Answer |
|----------|--------|
| Active providers hardened | Gemini, OpenAI, Anthropic/Claude (DeepSeek unchanged — multimodal blocked) |
| Payloads derive from manifest | Yes — `ProviderExecutionRequest` → `serialize_provider_images()` → adapter builders |
| Prompt/payload parity enforced | Yes — `validate_prompt_payload_manifest_parity()` before remote call |
| Provider position mapping available | Yes — `provider_image_manifest_order` in request metadata |
| Video changed | No |

**Risk:** Legacy `LLMRequest` list fields remain as compatibility projections behind `legacy_lists_from_provider_request()`; adapters without embedded provider request still use legacy builders (video path).

---

## 2. Active provider inventory

| Provider | Adapter | Production reachable | Visual support | Hardened |
| -------- | ------- | -------------------: | -------------: | -------: |
| Gemini | `GeminiSdkAdapter` / `GeminiGlobalAnalyzer` | yes | yes | yes |
| OpenAI | `OpenAiSdkAdapter` | yes | yes | yes |
| Claude | `AnthropicSdkAdapter` | yes | yes | yes |
| DeepSeek | `DeepSeekSdkAdapter` | yes | blocked for images | no (out of visual scope) |

---

## 3. Previous adapter risks

- Independent `frame_refs` / `context_images` lists built separately from manifest metadata
- Role grouping (references then primaries) reimplemented per adapter
- No pre-call parity validation between prompt IDs and serialized images
- `multimodal_order` could diverge from actual payload
- Evidence ID contract used `source_image_id` only

---

## 4. Canonical provider request

**Module:** `backend/src/pipeline/services/provider_execution_request.py`

- `ImageRuntimeResource` — provider-neutral runtime resource wrapper
- `ProviderExecutionImage` — manifest-aligned image binding
- `ProviderExecutionRequest` — immutable request contract
- `build_provider_execution_request()` — construction from manifest + bound payload
- `validate_provider_execution_request()` — invariant validation

**Bridge:** `backend/src/pipeline/services/provider_execution_bridge.py`

- `legacy_lists_from_provider_request()` — sole legacy list projection

**Serialization:** `backend/src/pipeline/services/provider_payload_serialization.py`

- `SerializedImagePayloadEntry`, `SerializedMultimodalPayload`
- `serialize_provider_images()`, `validate_prompt_payload_manifest_parity()`

---

## 5. Ordering contract

```text
manifest.payload_ordinal ascending
→ ProviderExecutionRequest.images (same order)
→ SerializedMultimodalPayload.entries (same order)
→ provider_image_position 0..N-1
→ adapter serialization (label + image pairs; no role-based reordering)
```

---

## 6. Provider-specific implementation

### Gemini
- `gemini_global_analyzer.py`: `resolve_serialized_payload_for_adapter()` → `build_gemini_contents_from_serialized()`
- Errors mapped to `LLMProviderError` in `gemini_sdk_adapter.py`

### OpenAI
- `openai_sdk_adapter.py` `_openai_build_user_content()`: serialized path → `build_openai_vision_from_serialized()`

### Anthropic/Claude
- `anthropic_sdk_adapter.py` `_anthropic_build_message_content()`: serialized path → `build_anthropic_vision_from_serialized()`

### Shared
- `vision_multimodal_payload.py` — centralized serialized builders + `resolve_serialized_payload_for_adapter()`

---

## 7. Provider parity matrix

| Provider | Manifest controls payload | Count verified | Order verified | Role verified | No hidden filtering |
| -------- | ------------------------: | -------------: | -------------: | ------------: | ------------------: |
| Gemini | yes | yes | yes | yes | yes |
| OpenAI | yes | yes | yes | yes | yes |
| Claude | yes | yes | yes | yes | yes |

---

## 8. Evidence identifier contract

| Item | Value |
|------|-------|
| Returned field (preferred) | `manifest_entry_id` (`EVIDENCE_RETURN_IDENTIFIER_FIELD`) |
| Legacy compatibility | `source_image_id` (`LEGACY_EVIDENCE_RETURN_FIELD`) |
| Normalization | `normalize_entity_evidence_identifiers()` in entity resolution |
| Reference rejection | `REF_*` resolves to reference `source_image_id` → INVALID |
| Unknown ID | `IMG_999` → INVALID |

**Schema:** `EntityV21.manifest_entry_id` added (optional); `source_image_id` retained.

---

## 9. Provider position metadata

**Key:** `provider_image_manifest_order`

**Stored in:** `LLMRequest.metadata` (set at strategy boundary and refreshed at adapter serialization)

**Example:**
```json
[
  {"provider_position": 0, "manifest_entry_id": "REF_001", "source_image_id": "ref-1", "role": "reference_image"},
  {"provider_position": 1, "manifest_entry_id": "IMG_001", "source_image_id": "asset-1", "role": "primary_evidence"}
]
```

---

## 10. Error handling

| Code | When |
|------|------|
| `PROVIDER_IMAGE_MANIFEST_MISMATCH` | Count/order/role/ID parity failure |
| `PROVIDER_IMAGE_SERIALIZATION_FAILED` | Empty/invalid ndarray encoding |
| `PROVIDER_IMAGE_UNSUPPORTED_FORMAT` | MIME not in supported set |
| `PROVIDER_IMAGE_RESOURCE_MISSING` | Runtime resource absent |
| `PROVIDER_IMAGE_LIMIT_EXCEEDED` | Reserved for provider limits (pre-manifest enforcement) |

Mapped to `LLMProviderError` at adapter boundary (no remote call).

---

## 11. Tests

**Added:**
- `tests/pipeline/test_provider_execution_request.py` (4)
- `tests/pipeline/test_provider_payload_parity.py` (3)
- `tests/pipeline/test_provider_multimodal_cross_provider.py` (1)
- `tests/pipeline/test_provider_execution_integration.py` (3)

**Updated:**
- `tests/pipeline/test_phase1_sent_frame_propagation.py`

**Commands:**
```bash
cd backend && python3 -m pytest \
  tests/domain/test_execution_image_manifest.py \
  tests/pipeline/test_execution_image_manifest_builder.py \
  tests/pipeline/test_execution_image_manifest_prompt.py \
  tests/pipeline/test_provider_execution_request.py \
  tests/pipeline/test_provider_payload_parity.py \
  tests/pipeline/test_provider_multimodal_cross_provider.py \
  tests/pipeline/test_provider_execution_integration.py \
  tests/domain/test_traceability_phase42.py \
  tests/pipeline/test_entity_resolution_phase42.py \
  tests/pipeline/test_execution_image_manifest_payload.py \
  -q --no-cov
```
**Result:** 55 passed, 0 failed, 0 skipped

**Worker / adapter regression:**
```bash
cd backend && python3 -m pytest \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/infrastructure/pipeline/test_worker_operational_safety_traceability_phase1.py \
  -q --no-cov
```
**Result:** 17 passed, 0 failed, 0 skipped

**Frontend regression:**
```bash
cd frontend && npm test -- --run \
  tests/evidenceEligibility.test.ts tests/resultMappers.test.ts \
  tests/ResultEvidencePanel.test.tsx tests/ResultEvidenceViewer.test.tsx
```
**Result:** 4 test files passed, 60 tests passed, 0 failed, 0 skipped

**compileall:** `PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q src` — success

---

## 12. Files changed

| Category | Files |
|----------|-------|
| Domain | `execution_image_manifest.py`, `manifest_evidence_resolution.py` |
| Pipeline | `provider_execution_request.py`, `provider_execution_errors.py`, `provider_payload_serialization.py`, `provider_execution_bridge.py`, `hybrid_global_analysis_strategy.py` |
| LLM | `vision_multimodal_payload.py`, `openai_sdk_adapter.py`, `anthropic_sdk_adapter.py`, `gemini_global_analyzer.py`, `gemini_sdk_adapter.py`, `enrichments.py` |
| Parsing | `global_analysis_parser.py`, `entity_resolution_stage.py` |
| Models | `schemas.py` (EntityV21) |
| Tests | 5 new/updated modules |
| Audit | this report |

---

## 13. Remaining risks

- Manifest not durable (`execution_image_manifest.json` — Phase 4.7)
- `Evidence.source_asset_id` not persisted (Phase 4.6)
- Legacy `LLMRequest` signatures retained; video path uses legacy builders without manifest contract
- DeepSeek visual path not hardened (explicitly blocked for multimodal jobs)
- Provider-specific image size downsampling still occurs at materialization (max_side) — does not alter count/order/identity

---

## 14. Phase 4.5 readiness

**Ready to start** Response Normalization and Evidence Reference Validation:

- Canonical `manifest_entry_id` contract in place
- Normalization to `source_image_id` before traceability
- Provider position metadata available for audit

**Prerequisites remaining:** durable manifest publication (optional for 4.5), structural evidence persistence (Phase 4.6).
