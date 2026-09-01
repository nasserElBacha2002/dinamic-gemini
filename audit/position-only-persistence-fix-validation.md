# POSITION_ONLY persistence fix — validation

**Date:** 2026-09-01  
**Status:** IMPLEMENTED_AND_VALIDATED (unit + cross-layer; live job UNVERIFIED pending new job)

## Root cause (confirmed)

```
CodeScanProcessingStrategy → RESOLVED_INTERNAL + evidence.result_kind=POSITION_ONLY
→ ProcessingResultPersister.persist()
→ _product_specs_from_result() empty
→ PersistSkipReason.MISSING_CODE_OR_QUANTITY
→ code_scan_asset_processor → PENDING_MANUAL_REVIEW / PROCESSING_INCOMPLETE_RESULT
```

Recognition was correct; persistence reinterpreted every RESOLVED result as product-centric.

## Fix summary

| Layer | Change |
|-------|--------|
| `processing_result_kind.py` | Typed helpers: `get_result_kind`, `requires_product_persistence`, `validate_position_only_evidence` |
| `processing_result_persister.py` | POSITION_ONLY branch: validate evidence + durable detections; write result-evidence acknowledgment (no empty ProductRecord); idempotent retry |
| `code_scan_asset_processor.py` | Map `POSITION_MATERIALIZATION_FAILED`; observability `code_scan.persistence_completed` metadata |
| `asset_processing_reconciler.py` | Recognize position-only complete state via detections + result evidence |
| `v3_image_processing_bridge.py` / `v3_job_executor.py` | Wire `position_detection_repo` into persister + reconciler |

## Migration

**NO_MIGRATION_REQUIRED** — runtime contract only.

## Tests executed

```bash
cd backend
.venv/bin/python -m pytest \
  tests/application/services/image_processing/test_position_only_persistence.py \
  tests/application/services/image_processing/test_processing_result_persister_needs_review.py \
  tests/application/services/image_processing/test_processing_result_persister_product_labels.py \
  tests/application/services/image_processing/test_asset_processing_reconciler.py \
  tests/unit/test_supplier_profile_runtime_wiring.py \
  --no-cov -q
```

**Result:** 28 passed

### Coverage by acceptance criterion

| # | Criterion | Test |
|---|-----------|------|
| 1–2 | POSITION_ONLY no internal_code/quantity | `test_position_only_persister_success_with_durable_detection` |
| 3 | Fail-closed without evidence/DB | `test_position_only_without_evidence_fails_closed`, `test_position_only_without_durable_detection_fails_closed` |
| 4 | Asset RESOLVED | `test_processor_position_only_finalizes_resolved` |
| 5–6 | No PROCESSING_INCOMPLETE_RESULT / MISSING_CODE_OR_QUANTITY for POSITION_ONLY | processor test + persister success |
| 7 | Position durable (detection table) | persister requires `ImagePositionLabelDetection` rows |
| 8 | No empty product_record | `product_repo.save.assert_not_called()` |
| 9–11 | Counters resolved=1, manual_review=0 | `aggregate_progress` in processor test |
| 12–16 | PRODUCT unchanged / incomplete fails | `test_product_persist_unchanged`, `test_product_result_still_requires_code_and_quantity` |
| 17 | Idempotency | `test_position_only_idempotent_second_persist` |
| 18 | Cross-layer | `test_processor_position_only_finalizes_resolved` |
| 19 | Live job | **UNVERIFIED** — requires new job after deploy + worker restart |

## SQL integration

**UNVERIFIED** — no SQL integration harness executed in this session. Memory + cross-layer unit tests cover the contract.

## Live verification steps (post-deploy)

1. Restart worker (`./dev.sh` or spawn worker for job).
2. Create **new** job on aisle `68a652c5-65f6-487d-a417-4349b8e3e81c` with POSITION asset payload `A04-R-02|04|RIGHT|02`.
3. Expect:
   - `job_asset_processing_states.status = RESOLVED`
   - `error_code IS NULL`
   - `image_position_label_detections` ≥ 1 row for asset
   - `result_evidence` acknowledgment row (no `positions`/`product_records` for POSITION_ONLY)
   - Job counters: `resolved=1`, `manual_review=0` (per asset)

## Files changed (this fix only)

- `backend/src/application/services/image_processing/processing_result_kind.py` (new)
- `backend/src/application/services/image_processing/processing_result_persister.py`
- `backend/src/application/services/image_processing/code_scan_asset_processor.py`
- `backend/src/application/services/image_processing/asset_processing_reconciler.py`
- `backend/src/infrastructure/pipeline/v3_image_processing_bridge.py`
- `backend/src/infrastructure/pipeline/v3_job_executor.py`
- `backend/tests/application/services/image_processing/test_position_only_persistence.py` (new)
