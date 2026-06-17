# Phase 4.4 — Provider Adapter Integration Hardening

## 1. Executive summary

**Verdict:** CORRECTIONS_VALIDATED (P0/P1 resolved; P2 applied)

| Question | Answer |
|----------|--------|
| Active providers hardened | Gemini, OpenAI, Anthropic/Claude (DeepSeek unchanged — multimodal blocked) |
| Payloads derive from manifest | Yes — `ProviderExecutionRequest` → `serialize_provider_images()` → adapter builders |
| Prompt/payload parity enforced | Yes — `validate_execution_projections_parity()` compares prompt/manifest/request/payload |
| Actual prompt composition validated | Yes — `PromptImageProjection` emitted by `enrich_prompt_with_execution_manifest()` |
| Provider position mapping available | Yes — `provider_image_manifest_order` in metadata (JSON-safe projection only) |
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
- `serialize_provider_images()`, `validate_execution_projections_parity()`

**Prompt projection:** `backend/src/domain/prompt_image_projection.py`

- `PromptImageProjection` — ordered/primary/reference manifest entry IDs + manifest version + optional section hash
- Built by `enrich_prompt_with_execution_manifest()` (same function that appends image sections)
- Stored in composition as `prompt_image_projection`

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
| Legacy compatibility | `source_image_id` (`LEGACY_EVIDENCE_RETURN_FIELD`) — input accepted when `manifest_entry_id` absent |
| Provider prompts | All active providers prefer `manifest_entry_id`; `source_image_id` optional/deprecated in schemas |
| Raw parsing | `RawEvidenceIdentifier` preserves both fields until validation |
| Normalization | `apply_evidence_resolution_to_entities()` in entity resolution |
| Conflict | Both fields resolve to different entries → INVALID + warning |
| Reference rejection | `REF_*` → INVALID |
| Unknown ID | `IMG_999` or unknown legacy → INVALID |

**Schema:** `EntityV21.manifest_entry_id` added (optional); `source_image_id` retained.

---

## 9. Provider position metadata

**Key:** `provider_image_manifest_order`

**Stored in:** `LLMRequest.metadata` (JSON-safe projection only; set at adapter serialization via `record_provider_image_manifest_order`)

**Runtime-only (excluded from metadata/logs/persistence):**
- `LLMRequest.provider_execution_request`
- `LLMRequest.serialized_multimodal_payload` (property; set at adapter boundary)

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

**Added (corrections):**
- `tests/domain/test_manifest_evidence_resolution.py` (8)
- `tests/pipeline/test_provider_metadata_serialization.py` (4)
- `tests/pipeline/test_provider_prompt_parity.py` (2)
- `tests/pipeline/test_provider_adapter_canonical_required.py` (3)
- `tests/pipeline/test_provider_mime_policy.py` (6)
- `tests/pipeline/test_provider_output_contract.py` (4)

**Updated:**
- `tests/pipeline/test_provider_execution_request.py`, `test_provider_payload_parity.py`, `test_provider_execution_integration.py`, `test_phase1_sent_frame_propagation.py`, `test_execution_image_manifest_prompt.py`, `test_provider_multimodal_cross_provider.py`, `test_claude_prompt_contract.py` (via hybrid_profiles)

**Commands (targeted — user spec):**
```bash
cd backend && python3 -m pytest \
  tests/domain/test_execution_image_manifest.py \
  tests/domain/test_manifest_evidence_resolution.py \
  tests/pipeline/test_execution_image_manifest_builder.py \
  tests/pipeline/test_execution_image_manifest_prompt.py \
  tests/pipeline/test_provider_execution_request.py \
  tests/pipeline/test_provider_payload_parity.py \
  tests/pipeline/test_provider_multimodal_cross_provider.py \
  tests/pipeline/test_provider_execution_integration.py \
  tests/pipeline/test_provider_metadata_serialization.py \
  tests/domain/test_traceability_phase42.py \
  tests/pipeline/test_entity_resolution_phase42.py \
  -q --no-cov
```
**Result:** 62 passed, 0 failed, 0 skipped

**Corrections extended (parity, canonical, MIME, provider contracts, worker):**
```bash
cd backend && python3 -m pytest \
  tests/pipeline/test_provider_prompt_parity.py \
  tests/pipeline/test_provider_adapter_canonical_required.py \
  tests/pipeline/test_provider_mime_policy.py \
  tests/pipeline/test_provider_output_contract.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/infrastructure/pipeline/test_worker_operational_safety_traceability_phase1.py \
  tests/llm/test_openai_sdk_adapter.py \
  tests/llm/test_anthropic_sdk_adapter.py \
  tests/llm/test_claude_prompt_contract.py \
  tests/pipeline/test_gemini_sdk_adapter.py \
  tests/llm/test_gemini_interleaved_adapter.py \
  tests/llm/test_gemini_global_analyzer_json_root.py \
  -q --no-cov
```
**Result:** 90 passed, 0 failed, 0 skipped (combined unique suite: 152 passed)

**Worker / adapter regression:**
```bash
cd backend && python3 -m pytest \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/infrastructure/pipeline/test_worker_operational_safety_traceability_phase1.py \
  -q --no-cov
```
**Result:** 19 passed, 0 failed, 0 skipped

**Frontend regression:**
```bash
cd frontend && npm test -- --run \
  tests/evidenceEligibility.test.ts tests/resultMappers.test.ts \
  tests/ResultEvidencePanel.test.tsx tests/ResultEvidenceViewer.test.tsx
```
**Result:** 4 test files passed, 60 tests passed, 0 failed, 0 skipped

**compileall:** `PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q src` — success

**ruff (correction-touched sources):** clean on changed modules; full-tree ruff not re-run (pre-existing repo warnings outside scope)

---

## 12. Files changed

| Category | Files |
|----------|-------|
| Domain | `prompt_image_projection.py`, `manifest_evidence_resolution.py`, `entity.py`, `traceability.py` |
| Pipeline | `provider_execution_request.py`, `provider_payload_serialization.py`, `hybrid_global_analysis_strategy.py`, `hybrid_analysis_prompt.py` |
| LLM | `types.py`, `vision_multimodal_payload.py`, `enrichments.py`, `hybrid_profiles.py`, `openai_sdk_adapter.py`, `anthropic_sdk_adapter.py`, `gemini_global_analyzer.py`, `gemini_sdk_adapter.py` |
| Parsing/Models | `global_analysis_parser.py`, `schemas.py` |
| Tests | 7 new + 8 updated modules |
| Audit | this report |

---

## 13. Remaining risks

- Manifest not durable (`execution_image_manifest.json` — Phase 4.7)
- `Evidence.source_asset_id` not persisted (Phase 4.6)
- Legacy `LLMRequest` signatures retained; video path uses legacy builders without manifest contract
- DeepSeek visual path not hardened (explicitly blocked for multimodal jobs)
- Provider-specific image size downsampling still occurs at materialization (max_side) — does not alter count/order/identity

---

## 14. Phase 4.4 corrections (code review follow-up)

### 14.1 Actual prompt parity implementation

`enrich_prompt_with_execution_manifest()` now returns `(prompt_text, PromptImageProjection)`. The projection is built from the same ordered manifest entries appended to the prompt (not reconstructed from `ProviderExecutionRequest`). It is stored in `composition["prompt_image_projection"]`.

`validate_execution_projections_parity()` (renamed from `validate_prompt_payload_manifest_parity`) compares four projections before remote execution:

1. `PromptImageProjection` (from composer)
2. Manifest composition projection
3. `ProviderExecutionRequest` image order/roles
4. `SerializedMultimodalPayload` entries

Failures raise `PROVIDER_IMAGE_MANIFEST_MISMATCH` (duplicate ID, missing ID, wrong role, order drift, version mismatch).

### 14.2 Final evidence identifier contract

| Layer | Contract |
|-------|----------|
| Model-facing (preferred) | `manifest_entry_id` (e.g. `IMG_001`) |
| Legacy input | `source_image_id` accepted when `manifest_entry_id` absent |
| Provider prompts/schemas | Gemini `EntityV21`, OpenAI suffix, Claude contract + JSON suffix all prefer `manifest_entry_id`; `source_image_id` optional/deprecated |
| Forbidden as primary evidence | `REF_*`, filenames, provider positions |

### 14.3 Conflict resolution matrix

| `manifest_entry_id` | `source_image_id` | Outcome |
|-------------------|-------------------|---------|
| absent | absent | MISSING |
| valid IMG_* | absent | RESOLVED via manifest |
| absent | valid legacy | RESOLVED via compatibility path |
| valid | valid, same entry | RESOLVED |
| valid | valid, different entries | INVALID + conflict warning |
| REF_* | any | INVALID (reference) |
| unknown IMG_* | any | INVALID (unknown) |
| any | unknown legacy | INVALID (unknown) |

### 14.4 Runtime vs serializable metadata boundary

**Runtime-only on `LLMRequest`:**
- `provider_execution_request: ProviderExecutionRequest | None`
- `serialized_multimodal_payload` (property; adapter boundary)

**Metadata retains JSON-safe projections only:**
- `provider_execution_request` snapshot (no runtime resources)
- `provider_image_manifest_order`, manifest version, image counts/IDs/roles
- `prompt_image_projection`, canonical flags

Removed `_provider_execution_request_object` and `_serialized_multimodal_payload` metadata keys.

### 14.5 Canonical-photo fallback policy

Photo V3 runs with execution manifest set:
- `canonical_provider_payload_required=True`
- `image_execution_contract="canonical_manifest"`

If manifest present but `provider_execution_request` missing → `PROVIDER_IMAGE_MANIFEST_MISMATCH` before remote call (Gemini, OpenAI, Anthropic). Legacy list builders remain only for deprecated/non-manifest paths (e.g. video).

### 14.6 MIME policy

When `declared_mime` is present: normalize and accept only supported image MIME types; unsupported values → `PROVIDER_IMAGE_UNSUPPORTED_FORMAT`. Infer from path/filename only when `declared_mime` is absent. No silent downgrade of PDF/TIFF/BMP to JPEG.

### 14.7 Cache policy

Cross-layer `_serialized_multimodal_payload` metadata caching removed. Serialization occurs once at adapter boundary; result stored on runtime `LLMRequest.serialized_multimodal_payload` property (not persisted).

### 14.8 Provider parity matrix (post-correction)

| Requirement | Gemini | OpenAI | Anthropic |
|-------------|--------|--------|-----------|
| Prompt projection matches manifest | yes | yes | yes |
| Request projection matches manifest | yes | yes | yes |
| Serialized payload matches manifest | yes | yes | yes |
| Provider position metadata matches order | yes | yes | yes |
| `manifest_entry_id` preferred in output contract | yes | yes | yes |
| Conflicting evidence fields rejected | yes | yes | yes |
| Canonical photo cannot downgrade to legacy | yes | yes | yes |
| Runtime objects excluded from metadata | yes | yes | yes |
| Unsupported declared MIME fails pre-call | yes | yes | yes |

### 14.9 Correction test results

See §11 — 62 targeted + 152 extended backend tests passed; frontend 60 passed; compileall success.

### 14.10 Remaining risks

- Manifest not durable on disk (Phase 4.7)
- `Evidence.source_asset_id` not persisted (Phase 4.6)
- DeepSeek visual path not hardened (blocked)
- Image max_side downsampling at materialization unchanged
- Full-tree mypy/ruff not enforced in this correction pass

---

## 15. Phase 4.5 readiness

**Ready to start** Response Normalization and Evidence Reference Validation:

- Canonical `manifest_entry_id` contract in place
- Normalization to `source_image_id` before traceability
- Provider position metadata available for audit

**Prerequisites remaining:** durable manifest publication (optional for 4.5), structural evidence persistence (Phase 4.6).
