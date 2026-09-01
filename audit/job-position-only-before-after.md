# Job POSITION_ONLY — before / after

## Reference job (before fix)

| Field | Value |
|-------|-------|
| Job | `68aae986-4429-40d5-9da1-4646a8f7e72f` |
| Asset | `ad40b787-081e-4551-a733-db3d5c06e004` |
| Payload | `A04-R-02\|04\|RIGHT\|02` |

## BEFORE

```
CODE_SCAN strategy
  → RESOLVED_INTERNAL
  → evidence.result_kind = POSITION_ONLY
  → error_code = null

ProcessingResultPersister
  → specs empty (no internal_code / quantity)
  → MISSING_CODE_OR_QUANTITY

code_scan_asset_processor
  → PENDING_MANUAL_REVIEW
  → PROCESSING_INCOMPLETE_RESULT

Observed counters
  → resolved = 0
  → manual_review = 1
  → positions (domain) = 0
  → product_records = 0
```

Position detections were written by `_materialize_supplier_positions` but asset state and counters treated the result as incomplete.

## AFTER (expected for new job)

```
CODE_SCAN strategy
  → RESOLVED_INTERNAL
  → evidence.result_kind = POSITION_ONLY

ProcessingResultPersister
  → validate position evidence + durable detections
  → write result_evidence acknowledgment (idempotent)
  → persisted=True, products_persisted=0, positions_persisted=1

code_scan_asset_processor
  → finalize_from_result → RESOLVED
  → attempt SUCCEEDED

Observed counters (expected)
  → resolved = 1
  → manual_review = 0
  → unrecognized = 0 (for this asset)
  → image_position_label_detections = 1
  → product_records = 0
  → positions table = 0 (by design — shelf Position entity is product-centric)
```

## Note on `positions` counter semantics

- **Position label detections** (`image_position_label_detections`) are the authoritative durable record for POSITION_ONLY.
- **Domain `positions` table** remains product-centric (Position + ProductRecord UoW); POSITION_ONLY does not create an empty product row.
- UI/domain metrics that count “detecciones de posición” should use detections or job progress `resolved`, not `product_records`.

## Do not re-use job `68aae986-...`

That job’s `job_asset_processing_states` row was finalized under the old semantics. Validate with a **new job** after deploying this fix.
