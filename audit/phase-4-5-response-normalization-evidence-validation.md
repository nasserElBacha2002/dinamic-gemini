# Phase 4.5 — Response Normalization and Evidence Reference Validation

## 1. Executive summary

**Verdict:** COMPLETE_WITH_RISKS

| Item | Status |
|------|--------|
| Manifest-aware response normalization | Yes |
| `manifest_entry_id` preferred | Yes |
| Legacy `source_image_id` compatibility | Yes |
| Conflicting fields rejected | Yes |
| Raw provider IDs blocked from `source_image_id` | Yes (corrections) |
| Explicit `manifest_required` for photo V3 | Yes (corrections) |
| Provider-specific response shape fixtures | Yes (corrections) |
| Merge helpers wired into runtime consolidation | **No** (documented risk) |
| `execution_log` durable publication regressed | No |
| Gemini serialized payload regressed | No |
| Video traceability implemented | No |
| Phase 4.6 started | No |

## 2. Previous response-side risks

| Risk | Mitigation |
|------|------------|
| Ambiguous `source_image_id` | `raw_source_image_id` preserved; stable ID only after resolution |
| Lost `manifest_entry_id` | Parser + normalizer preserve field |
| Provider schema drift | Central resolver + provider fixture tests |
| Reference promotion | REF_* → INVALID |
| Merge overwriting VALID | `merge_evidence_resolution_results` + `merge_entity_evidence_fields` |
| Silent conflict acceptance | Both-fields conflict → INVALID |

## 3. Raw evidence contract

| Field | Role |
|-------|------|
| `manifest_entry_id` (raw on Entity) | Preferred provider evidence identifier |
| `raw_source_image_id` | Legacy provider `source_image_id` before resolution |
| `resolved_manifest_entry_id` | Canonical manifest entry after validation |
| `source_image_id` | Stable source image ID **only** after primary evidence resolution (never raw provider value; never reference/invalid resolved ID) |
| `traceability_status` / `traceability_warning` | Fail-closed traceability outcome |

## 4. Resolution matrix (summary)

| manifest_entry_id | source_image_id | Manifest | Result |
|-------------------|-----------------|----------|--------|
| IMG_001 (primary) | — | valid | RESOLVED → VALID after sent-frame check |
| — | asset-1 (primary) | valid | RESOLVED (legacy compat) |
| IMG_001 | asset-1 (same) | valid | RESOLVED |
| IMG_001 | ref-1 (different) | valid | INVALID conflict |
| REF_001 | — | valid | INVALID reference |
| IMG_999 | — | valid | INVALID unknown |
| filename.jpg | — | valid | INVALID malformed |
| — | — | valid | MISSING |
| IMG_001 | — | missing | UNVALIDATED |
| IMG_001 | — | corrupt | UNVALIDATED |

## 5. Provider coverage

| Provider | manifest_entry_id | legacy source_image_id | conflict rejected |
|----------|------------------:|-----------------------:|------------------:|
| Gemini | Yes | Yes | Yes |
| OpenAI | Yes | Yes | Yes |
| Claude | Yes | Yes | Yes |

## 6. Merge policy

1. VALID beats MISSING/INVALID
2. VALID + VALID different sources → keep first deterministically + warning
3. INVALID + MISSING → INVALID
4. RESOLVED (outcome) beats LEGACY_DEFERRED and INVALID when ranking merge candidates
5. MISSING beats LEGACY_DEFERRED (explicit status outranks deferred)
6. Conflicting raw IDs preserved in warnings when merge occurs

**Runtime integration:** `merge_evidence_resolution_results` and `merge_entity_evidence_fields` are implemented and unit-tested but **not wired** into a live duplicate-entity consolidation stage in Phase 4.5. Runtime merge behavior is therefore not fully governed by this policy until a future stage wires these helpers.

## 7. Reporting/persistence fields

Carried in `hybrid_report` and `v3_report_mapper` detected summary:

- `manifest_entry_id`, `raw_source_image_id`, `resolved_manifest_entry_id`
- `source_image_id`, `traceability_status`, `traceability_warning`
- `has_valid_evidence` (fail-closed derived)

No database migrations (Phase 4.6).

## 8. Artifact/finalization regression

Phase 4.5 did **not** modify artifact publication, execution_log, or finalization logic.

Regression tests passed:

- `test_execution_log_json_safety.py`
- `test_execution_log_durable_publication_flow.py`
- `test_gemini_serialized_materialization.py`
- `test_provider_payload_parity.py`
- `test_phase45_metadata_artifact_regression.py`

## 9. Tests

### Added

- `tests/parsing/test_global_analysis_parser_evidence_ids.py` (4)
- `tests/pipeline/test_entity_resolution_phase45.py` (3)
- `tests/domain/test_evidence_merge_phase45.py` (4)
- `tests/pipeline/test_provider_response_normalization_phase45.py` (12 parametrized)
- `tests/pipeline/test_phase45_metadata_artifact_regression.py` (2)

### Updated

- `tests/domain/test_manifest_evidence_resolution.py`
- `tests/pipeline/test_phase1_sent_frame_propagation.py`

### Commands and exact results

```bash
cd backend && python3 -m pytest \
  tests/domain/test_manifest_evidence_resolution.py \
  tests/parsing/test_global_analysis_parser_evidence_ids.py \
  tests/pipeline/test_entity_resolution_phase45.py \
  tests/pipeline/test_provider_execution_integration.py \
  tests/domain/test_traceability_phase42.py \
  tests/pipeline/test_entity_resolution_phase42.py \
  tests/pipeline/test_provider_payload_parity.py \
  tests/pipeline/test_provider_multimodal_cross_provider.py \
  tests/domain/test_evidence_merge_phase45.py \
  tests/pipeline/test_provider_response_normalization_phase45.py \
  tests/pipeline/test_phase45_metadata_artifact_regression.py \
  tests/llm/test_gemini_serialized_materialization.py \
  tests/pipeline/test_execution_log_json_safety.py \
  tests/pipeline/test_execution_log_artifact_publication.py \
  tests/infrastructure/pipeline/test_execution_log_durable_publication_flow.py \
  tests/pipeline/test_provider_metadata_serialization.py \
  tests/llm/test_vision_multimodal_payload.py \
  tests/pipeline/test_phase1_sent_frame_propagation.py \
  tests/infrastructure/pipeline/test_worker_phase3_part5_artifact_outbox.py \
  -q --no-cov
```

**Result:** 120 passed, 1 skipped, 0 failed

```bash
cd frontend && npm test -- --run \
  tests/evidenceEligibility.test.ts \
  tests/resultMappers.test.ts \
  tests/ResultEvidencePanel.test.tsx \
  tests/ResultEvidenceViewer.test.tsx
```

**Result:** 60 passed, 0 failed

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q src
```

**Result:** success

## 10. Files changed

| Area | Files |
|------|-------|
| Domain | `manifest_evidence_resolution.py`, `entity.py`, `traceability.py` |
| Parsing | `global_analysis_parser.py` |
| Normalization | `entity_normalizer.py` |
| Reporting | `hybrid_report.py`, `v3_report_mapper.py` |
| Tests | 7 new/updated test modules |

## 11. Remaining risks

- Structural evidence persistence (Phase 4.6) not implemented
- Durable manifest artifact (Phase 4.7) not implemented
- API/frontend final contract (Phase 4.8) not implemented
- **Merge policy helpers are not wired into live duplicate-entity consolidation** — evidence may still be overwritten incorrectly if a runtime merge stage exists without these helpers

## 12. Phase 4.5 code-review corrections (post CHANGES_REQUESTED)

### 12.1 `source_image_id` raw contamination fix

`apply_traceability_validation()` no longer copies `raw_source_image_id` into `source_image_id` when sent-frame metadata is unavailable. Raw provider values remain in `raw_source_image_id` only; `source_image_id` stays `None` until manifest resolution produces a stable primary evidence ID.

### 12.2 Explicit `manifest_required` behavior

`apply_evidence_resolution_to_entities(..., manifest_required: bool | None = None)`:

| Value | Behavior |
|-------|----------|
| `True` | Missing or corrupt canonical manifest → `UNVALIDATED` (fail-closed) |
| `False` | Legacy compatibility: resolution may defer (`LEGACY_DEFERRED`) without manifest |
| `None` | Backward-compatible: infers requirement from composition manifest key presence |

`EntityResolutionStage` passes `manifest_required=True` for active photo V3 jobs (`input_type == "photos"`).

### 12.3 Provider-specific fixture coverage

Added `tests/pipeline/test_provider_response_shapes_phase45.py` with per-provider shape wrappers (Gemini canonical, OpenAI qty alias, Claude label noise) covering eight evidence scenarios each. Existing `test_provider_output_contract.py` validates schema/suffix contract (manifest_entry_id preferred, source_image_id optional).

### 12.4 Merge ranking correction

`merge_evidence_resolution_results()` ranks each `EvidenceResolutionResult` individually via `_rank(result)` using outcome and status, not outer-scope variables.

### 12.5 Merge runtime integration status

**Not integrated** — verdict downgraded to `COMPLETE_WITH_RISKS` (see §6).

### 12.6 Invalid/reference `source_image_id` policy

`Entity.source_image_id` is populated **only** when resolution outcome is `RESOLVED` (primary evidence). INVALID, reference, conflict, and malformed cases set `source_image_id = None`; audit fields (`raw_source_image_id`, `resolved_manifest_entry_id`, warnings) are preserved.

### 12.7 Malformed manifest entry ID classification

Case-sensitive format: `IMG_\d+` (primary), `REF_\d+` (reference). Wrong casing (`img_001`) and non-manifest strings (`filename.jpg`) → `INVALID_MALFORMED`; well-formed unknown (`IMG_999`) → `INVALID_UNKNOWN`.

### 12.8 Artifact/Gemini regression (corrections pass)

| Suite | Result |
|-------|--------|
| Phase 4.5 targeted backend | 108 passed, 0 failed |
| Artifact/Gemini regression | 58 passed, 1 skipped, 0 failed |
| Frontend regression | 60 passed, 0 failed |
| `compileall src` | success |

## 13. Phase 4.6 readiness

**Ready for planning.** Phase 4.5 provides:

- Stable `source_image_id` and `resolved_manifest_entry_id`
- Raw evidence fields for audit
- Deterministic traceability status/warnings
- JSON-safe metadata for downstream persistence work

Prerequisite for 4.6: map resolved fields into `Evidence` structural model and DB schema.
