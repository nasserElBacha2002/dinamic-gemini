# Phase 4.5 — Response Normalization and Evidence Reference Validation

## 1. Executive summary

**Verdict:** COMPLETE

| Item | Status |
|------|--------|
| Manifest-aware response normalization | Yes |
| `manifest_entry_id` preferred | Yes |
| Legacy `source_image_id` compatibility | Yes |
| Conflicting fields rejected | Yes |
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
| `source_image_id` | Stable source image ID only after resolution |
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
4. Conflicting raw IDs preserved in warnings when merge occurs

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
- Entity merge utilities exist but are not wired into a live duplicate-entity consolidation stage

## 12. Phase 4.6 readiness

**Ready for planning.** Phase 4.5 provides:

- Stable `source_image_id` and `resolved_manifest_entry_id`
- Raw evidence fields for audit
- Deterministic traceability status/warnings
- JSON-safe metadata for downstream persistence work

Prerequisite for 4.6: map resolved fields into `Evidence` structural model and DB schema.
