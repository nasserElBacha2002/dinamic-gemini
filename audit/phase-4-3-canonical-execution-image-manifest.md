# Phase 4.3 — Canonical Execution Image Manifest

## 1. Executive summary

**Verdict:** COMPLETE (corrections pass applied)

Phase 4.3 introduces a single immutable runtime contract (`ExecutionImageManifest`) for photo-based V3 executions. The manifest is built after frame acquisition and reference resolution, then drives prompt composition, derived compatibility metadata, traceability validation, and **provider-bound payload materialization**.

| Question | Answer |
|----------|--------|
| Canonical manifest introduced? | Yes — `ExecutionImageManifest`, `ExecutionImageEntry`, `ExcludedExecutionImage` |
| Prompt and payload share one source of truth? | Yes — `bind_provider_payload_from_manifest()` materializes `frame_paths`, `frames_nd`, `frame_refs`, `context_images`, `reference_image_ids` from manifest; adapters validate lists against embedded manifest |
| Traceability uses manifest? | Yes — manifest-aware extraction; corrupt serialized manifest fails closed (no `frames_sent_ids` fallback) |
| Evidence return contract? | `source_image_id` (`EVIDENCE_RETURN_IDENTIFIER_FIELD`) — stable asset UUID, not `manifest_entry_id` |
| Video changed? | No |

**Phase 4.4:** Not started beyond minimum manifest consumption in hybrid strategy and prompt builder.

---

## 2. Previous fragmentation

Before Phase 4.3, image identity was passed through parallel structures:

| Structure | Risk |
|-----------|------|
| `frame_paths` / `frames_nd` | Loaded images without explicit role |
| `frame_refs` | Primary IDs passed separately from prompt |
| `prompt_listed_image_ids` | Could diverge from sent set |
| `frames_sent_ids` | Metadata copy of frame refs |
| `reference_image_ids` | Resolved separately in visual bundle |
| Provider multimodal order | Built independently in each adapter |

These could drift when caps, decode failures, or reference loading changed the effective execution set.

---

## 3. Canonical contract

**Module:** `backend/src/domain/execution_image_manifest.py`

```python
@dataclass(frozen=True)
class ExecutionImageManifest:
    job_id: str
    entries: tuple[ExecutionImageEntry, ...]
    excluded_entries: tuple[ExcludedExecutionImage, ...]
    version: int = 1
```

- **Roles:** `PRIMARY_EVIDENCE`, `REFERENCE_IMAGE`
- **Model-facing IDs:** `IMG_001`, `IMG_002`, `REF_001` (deterministic)
- **Stable IDs:** `source_asset_id`, `source_image_id` (unchanged asset UUIDs for traceability)
- **Validation:** `validate_execution_image_manifest()` — unique ordinals, contiguous ordering, no excluded/active overlap, at least one primary
- **Error type:** `ExecutionImageManifestError`

---

## 4. Construction flow

```
PhotosFrameSource.get_frames
→ FrameAcquisitionStage (cap, decode, exclusions → metadata.manifest_exclusions)
→ HybridGlobalAnalysisStrategy._analyze_once
    → prepare_visual_reference_inputs
    → build_execution_image_manifest (builder)
    → bind_provider_payload_from_manifest (payload authority)
    → build_hybrid_analysis_prompt_with_traceability(execution_manifest=...)
    → traceability_metadata_payload (derived from manifest projection)
→ Provider adapters (validate frame_refs / reference_image_ids against manifest in metadata)
→ EntityResolutionStage (manifest-aware traceability extraction)
```

**Builder:** `backend/src/pipeline/services/execution_image_manifest_builder.py`

**Payload binding:** `backend/src/pipeline/services/execution_image_manifest_payload.py`

---

## 5. Identity model

| Concept | Field | Example |
|---------|-------|---------|
| Source asset | `source_asset_id` | `img_001` (upload asset ID) |
| Provider-returned evidence ID | `source_image_id` | stable asset UUID (`EVIDENCE_RETURN_IDENTIFIER_FIELD`) |
| Model-facing entry ID | `manifest_entry_id` | `IMG_001` |
| Payload order | `payload_ordinal` | 1..N (references first, then primaries) |
| Role | `role` | `primary_evidence` / `reference_image` |

---

## 6. Prompt integration

`enrich_prompt_with_execution_manifest()` appends:

```text
PRIMARY EVIDENCE IMAGES
- IMG_001 (source_image_id='asset-uuid', ...)

REFERENCE IMAGES (classification context only)
- REF_001 (source_image_id='ref-uuid', ...)
```

Compatibility projections (derived, not independently authored):

- `frames_sent_ids` ← primary `source_image_id` values
- `prompt_listed_image_ids` ← manifest entry IDs (`IMG_*`, `REF_*`)
- `reference_image_ids` ← reference `source_image_id` values
- `execution_image_manifest` ← full serialized manifest

---

## 7. Provider integration

| Provider | Manifest authority | Adapter validation | Order |
|----------|-------------------|-------------------|-------|
| Gemini | `bind_provider_payload_from_manifest` at strategy | `validate_provider_lists_against_request_manifest` | references → primaries |
| OpenAI | same | same | same |
| Claude/Anthropic | same | same | same |

Adapters still accept legacy list parameters for compatibility; when `execution_image_manifest` is embedded in request metadata, adapter entry validates lists match manifest exactly.

`manifest_bound_multimodal_order` in request metadata records `(role, source_image_id, provider_position)` for diagnostics.

---

## 8. Traceability integration

- **Valid primary set:** `manifest.primary_source_image_ids()`
- **Reference set:** `manifest.reference_source_image_ids()`
- **Excluded:** never in active entries; returned IDs → INVALID
- **Missing manifest:** falls back to `frames_sent_ids` (Phase 4.2 fail-closed preserved)
- **Corrupt manifest key present:** fail closed — `extract_sent_image_ids_from_composition` returns `None` (UNVALIDATED); no silent legacy fallback
- **`prompt_listed_image_ids`:** never authorizes VALID

---

## 9. Compatibility fields

Retained as derived projections only:

- `frames_sent_ids`
- `prompt_listed_image_ids` (now manifest entry IDs in prompt)
- `reference_image_ids`
- `multimodal_order` (adapter-populated, unchanged)

---

## 10. Tests

**Added:**
- `tests/domain/test_execution_image_manifest.py` (version hardening, validation)
- `tests/pipeline/test_execution_image_manifest_builder.py` (duplicate first-wins)
- `tests/pipeline/test_execution_image_manifest_prompt.py` (2 tests)
- `tests/pipeline/test_execution_image_manifest_payload.py` (6 tests — bind + adapter validation)

**Updated:**
- `tests/pipeline/test_phase1_sent_frame_propagation.py` (manifest entry ID + `manifest_bound_multimodal_order`)
- `tests/domain/test_traceability_phase42.py` (manifest precedence + corrupt manifest fail-closed)

**Commands:**
```bash
cd backend && python3 -m pytest \
  tests/domain/test_execution_image_manifest.py \
  tests/pipeline/test_execution_image_manifest_builder.py \
  tests/pipeline/test_execution_image_manifest_payload.py \
  tests/pipeline/test_execution_image_manifest_prompt.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/pipeline/test_entity_resolution_phase42.py \
  tests/domain/test_traceability_phase42.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/infrastructure/pipeline/test_worker_operational_safety_traceability_phase1.py \
  -q --no-cov
```
**Result:** 63 passed, 0 failed, 0 skipped

**Frontend regression (Phase 4.2 evidence):**
```bash
cd frontend && npm test -- --run tests/evidenceEligibility.test.ts tests/resultMappers.test.ts tests/ResultEvidencePanel.test.tsx tests/ResultEvidenceViewer.test.tsx
```
**Result:** 4 test files passed, 60 tests passed

**Build:** `npm run build` — success

**compileall:** blocked by sandbox permission on system pyc cache (environment limitation)

---

## 11. Files changed

| Category | Files |
|----------|-------|
| Domain | `execution_image_manifest.py`, `traceability.py` |
| Pipeline | `execution_image_manifest_builder.py`, `execution_image_manifest_payload.py`, `hybrid_global_analysis_strategy.py`, `hybrid_analysis_prompt.py`, `frame_acquisition_stage.py` |
| LLM | `vision_multimodal_payload.py`, `openai_sdk_adapter.py`, `anthropic_sdk_adapter.py`, `gemini_global_analyzer.py` |
| Prompt | `enrichments.py` |
| Tests | 6 new/updated test modules |
| Audit | this report |

---

## 12. Corrections pass (code review)

| Finding | Resolution |
|---------|------------|
| P0 — manifest descriptive only | `bind_provider_payload_from_manifest()` replaces legacy lists before `LLMRequest` |
| P0 — order ambiguity | Single manifest `payload_ordinal`; adapter validates `frame_refs` / `reference_image_ids` |
| P1 — evidence ID contract | `EVIDENCE_RETURN_IDENTIFIER_FIELD = "source_image_id"` in prompt enrichment |
| P1 — corrupt manifest silent fallback | `require_manifest_from_composition()`; traceability fail-closed when key present but invalid |
| P1 — duplicate candidates | First wins; later duplicates → `ExcludedExecutionImage(DUPLICATE)`; validation allows active+duplicate exclusion overlap |
| P1 — version hardening | `from_dict()` requires `version`; rejects unsupported versions |
| P1 — provider regression tests | `test_execution_image_manifest_payload.py` + OpenAI builder manifest validation tests |

---

## 13. Remaining risks

- Manifest not yet durable (`execution_image_manifest.json` — Phase 4.7)
- `Evidence.source_asset_id` not wired (Phase 4.6)
- Provider adapters still accept legacy list parameters (manifest object not passed directly — Phase 4.4)
- Pre-existing frontend `typecheck` fixture gaps unchanged
- Video path unchanged (deprecated, out of scope)

---

## 14. Phase 4.4 readiness

**Ready to start** provider adapter hardening:

- Pass manifest object into adapters
- Assert payload ordinal ↔ manifest entry mapping at adapter boundary
- Remove redundant independent list construction inside adapters
- Add per-provider ordering regression tests

Phase 4.3 delivers the canonical contract and single construction point; Phase 4.4 completes adapter-level enforcement.

**Video traceability:** Not implemented.
