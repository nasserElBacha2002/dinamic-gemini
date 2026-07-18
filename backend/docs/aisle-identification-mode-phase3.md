# Aisle identification — Phase 3 (CODE_SCAN per-image processing)

## Goal

Add a deterministic, auditable **CODE_SCAN** execution strategy that reads the internal
code and quantity from each aisle photo's QR / CODE128 label — **without** OCR, LLM, or any
guessing. One physical image maps to at most one position.

## Hard constraints

- **No OCR, no LLM fallback, no multi-label per image, no dedupe by code.**
- Physical rule: ONE image → at most ONE position (`SINGLE_ASSET` scope).
- Missing / invalid quantity with a recoverable code → `PENDING_MANUAL_REVIEW`
  (quantity is **never** defaulted to 1).
- Two different assets carrying the same code → two positions (no dedupe).
- The Phase 1/2 `LEGACY_LLM` / `AISLE_BATCH` path is untouched.

## Payload grammar (reused from `code_scan_qr_payload.parse_inventory_code_payload`)

| Format | Example | Result |
|--------|---------|--------|
| Pipe (primary) | `internal_code|quantity` e.g. `ABC123|5` | code + qty |
| DI1 legacy | `DI1|C=<urlencoded>|Q=<qty>` | code + qty |
| Plain / labelled | `ABC123` | code, qty = None → manual review |

Quantity: positive integers only, `1..CODE_SCAN_QUANTITY_MAX`, no decimals. Leading zeros in
the **code** are preserved.

## Architecture

```text
V3JobExecutor._v3_run_job_body
  └─ execution_strategy == CODE_SCAN and CODE_SCAN_PROCESSING_ENABLED
        → _run_code_scan_path
            → AisleProcessingOrchestrator.process_with_code_scan   (no JobProcessingLease)
                → ensure JobAssetProcessingState rows
                → recover abandoned PROCESSING states
                → ThreadPool(max_workers = MAX_IMAGE_PROCESSING_CONCURRENCY)
                    per PENDING asset:
                      acquire (PENDING only, worker_token)
                      create ProcessingAttempt STARTED (SINGLE_ASSET, logical=False)
                      CodeScanProcessingStrategy.process(context, asset)
                        → SourceAssetContentReader.read_image_bytes
                        → CodeScannerPort.scan_asset (pyzbar; 0° then optional 90/180/270)
                        → EncodedLabelPayloadParser.parse per detection
                        → CodeDetectionConsolidator.consolidate
                      if RESOLVED_INTERNAL → ProcessingResultPersister.persist
                      finalize_from_result (optimistic version + worker_token)
                → finalize_code_scan_success (job SUCCEEDED, aisle processed, no LLM report)
```

### Result status mapping

| Consolidation | ImageResultStatus | Position created |
|---------------|-------------------|------------------|
| Exactly one valid code + qty | `RESOLVED_INTERNAL` | yes (AUTOMATIC) |
| No detection / no valid code | `UNRECOGNIZED` | no |
| Missing / invalid qty, code ok | `PENDING_MANUAL_REVIEW` | no |
| Quantity conflict / multiple distinct codes | `PENDING_MANUAL_REVIEW` | no |
| Missing file / corrupt image / scanner unavailable / timeout | `FAILED_TECHNICAL` | no |

### Persistence & idempotency

`ProcessingResultPersister` reuses the **manual image-result unit of work** so a code-scan
position and an operator manual result can never both exist for the same
`(job_id, source_asset_id)`. It acquires the image-result lock, checks manual coverage +
existing results, then writes `Position` (AUTOMATIC, `DETECTED`, `needs_review=false`,
confidence 1.0), `ProductRecord` (`sku=internal_code`, `detected_quantity`,
`qty_source="label_explicit"`), `Evidence` (ORIGINAL_IMAGE, primary), a
`ResultEvidenceRecord` (`provider="code_scan"`), and a `ManualImageCoverageLink`
(uniqueness). Re-running the same job/asset is a no-op (reconcile).

Quantity is written as an **int** only: a float that is a whole number (`5.0`) is accepted and
converted, but a real decimal (`2.7`) is **rejected** (never truncated) and routed to manual
review. Booleans are rejected.

### PersistOutcome invariants (Phase 3 corrections)

`persist(...)` returns a `PersistOutcome(persisted, reconciled, position_id, active_result_id,
skipped_reason)`. The per-asset processor **must honor it**:

| `skipped_reason` | meaning | asset finalized as |
|------------------|---------|--------------------|
| — (`persisted=True`) | new position written | `RESOLVED_INTERNAL` (`active_result_id` set) |
| `ALREADY_PERSISTED` (`reconciled=True`) | a prior code-scan position exists | `RESOLVED_INTERNAL` (reconciled) |
| `CONCURRENCY_CONFLICT` (`reconciled=True`) | lost a race but winner's position found | `RESOLVED_INTERNAL` (reconciled) |
| `MANUAL_RESULT_EXISTS` | an operator manual result owns the image | `PENDING_MANUAL_REVIEW` (`MANUAL_RESULT_EXISTS`) |
| `ASSET_NOT_IN_SNAPSHOT` | asset missing from job snapshot | `FAILED_TECHNICAL` (`ASSET_NOT_IN_JOB_SNAPSHOT`) |
| `MISSING_CODE_OR_QUANTITY` / `NON_POSITIVE_QUANTITY` | incomplete result | `PENDING_MANUAL_REVIEW` (`CODE_SCAN_INCOMPLETE_RESULT`) |
| `CONCURRENCY_CONFLICT` (unreconciled) / other | no position exists | `FAILED_TECHNICAL` (`CODE_SCAN_PERSISTENCE_FAILED`) |

**Hard invariant:** an asset is NEVER finalized `RESOLVED` when `persisted=False` and
`reconciled=False`. A missing strategy or persister raises
`CodeScanPipelineMisconfiguredError` up front and the job is failed
(`CODE_SCAN_PIPELINE_MISCONFIGURED`) — the path never runs half-wired.

### Reconciliation & recovery

`AssetProcessingReconciler` looks up an already-persisted result (manual coverage link, then
valid result-evidence) for `(job_id, source_asset_id)`. It runs **before** scanning (skip the
scan and finalize `RESOLVED` if a complete result already exists) and **before** recovering an
abandoned `PROCESSING` state to `PENDING` (reconcile straight to `RESOLVED` instead of a
wasteful rescan). After a successful persist, a lost `finalize` race (`state_conflict`) is
reconciled rather than downgraded, and the orphaned attempt is closed
(`RECONCILED_BY_OTHER_WORKER`).

### Job outcome policy

`code_scan_job_outcome_policy.decide(progress, cancelled, infrastructure_error)` maps terminal
per-asset counters to a single `CodeScanJobOutcome`:

- `CANCELLED` → cancellation coordinator.
- `FAILED` (infra error, all failed, or any asset left PENDING/PROCESSING) → `fail_job_and_aisle`.
- `PARTIALLY_COMPLETED` (some failed + some productive) → `finalize_code_scan_success` with
  `result_json.code_scan_outcome="PARTIALLY_COMPLETED"` and `code_scan_partial=true`. A partial
  run is still a **completed** job with a mix of asset outcomes.
- `SUCCEEDED` (incl. all-unrecognized or all-manual-review, and empty aisle) →
  `finalize_code_scan_success`.

`ok` is true only for `SUCCEEDED`/`PARTIALLY_COMPLETED`; the executor never reports success for
a `FAILED` outcome.

### Evidence & privacy

Per-detection evidence carries `scanner_name`, `scanner_version`, `symbology`,
`bounding_box`, `detection_count`, and `raw_value_hash` (SHA-256 hex). The **raw payload is
never logged** or stored in cleartext in evidence.

## Feature flags (defaults safe)

| Env | Default | Role |
|-----|---------|------|
| `CODE_SCAN_PROCESSING_ENABLED` | false | Master switch for the CODE_SCAN strategy |
| `MAX_IMAGE_PROCESSING_CONCURRENCY` | 1 | ThreadPool workers for SINGLE_ASSET code scan. **Keep 1 in production** until SQL concurrency tests pass; values > 1 rely on the `ManualImageResultUnitOfWork` creating its own connection per `with uow` |
| `CODE_SCAN_MAX_IMAGE_SIDE` | 2048 | Downscale before rotated-variant scanning |
| `CODE_SCAN_VARIANTS_BUDGET_SECONDS` | 15 | Wall-clock budget checked **between** scan variants; does NOT interrupt a blocked native decode. (Alias: deprecated `CODE_SCAN_TIMEOUT_SECONDS`.) |
| `CODE_SCAN_ENABLE_ROTATIONS` | true | Retry 90/180/270 when 0° finds nothing |
| `CODE_SCAN_MAX_VARIANTS` | 4 | Max scan variants (0/90/180/270) |
| `CODE_SCAN_QUANTITY_MAX` | 99999999 | Max accepted positive-integer quantity |

Not exposed (setting them has no effect; coerced to safe defaults with a warning/error log):
`CODE_SCAN_ALLOW_DECIMAL_QUANTITY` (decimals unsupported), `CODE_SCAN_ENABLE_PREPROCESSING`
(preprocessing not implemented), `CODE_SCAN_MAX_TECHNICAL_ATTEMPTS` (no transient-retry loop).

`execution_strategy` is resolved at job start by
`resolve_execution_strategy(effective_mode, pipeline_enabled, code_scan_processing_enabled)`
and snapshotted immutably on the job.

## Migrations

- `0053_code_scan_processing_strategy.sql` — widens the `inventory_jobs.execution_strategy`
  CHECK to include `CODE_SCAN` (drop/recreate, idempotent) and adds the optional
  `job_asset_code_scan_detections` audit table. The sync-API `aisle_code_scan_detections`
  table is left untouched. Mirrored in `schema.sql`.
- `0054_code_scan_state_execution_scope_check.sql` — additive + idempotent. Defensively
  ensures `job_asset_processing_states.active_result_id` and `.execution_scope` exist (both
  from 0051) and adds `CK_job_asset_processing_states_execution_scope` constraining
  `execution_scope` to `NULL | AISLE_BATCH | SINGLE_ASSET`. The unique manual-coverage index
  already exists on `manual_image_coverage`. Mirrored in `schema.sql`.

## Deployment

`Dockerfile.worker` now installs `libzbar0` and verifies `pyzbar` importability at build
time (previously API-only). Without it, code scan surfaces `FAILED_TECHNICAL` per asset.

## Limitations (explicit)

- **No OCR and no LLM fallback**: if the label has no machine-readable QR/CODE128 the asset
  is `UNRECOGNIZED` (never sent to an LLM).
- The variants budget (`CODE_SCAN_VARIANTS_BUDGET_SECONDS`) is a **wall-clock budget checked
  between scan variants** — it does NOT interrupt a blocked native `pyzbar` decode already in
  progress (no process-pool hard timeout in this phase).
- `CODE_SCAN_ENABLE_PREPROCESSING` and `CODE_SCAN_MAX_TECHNICAL_ATTEMPTS` remain as reserved
  settings but have no effect (no preprocessing filters, no transient-retry loop);
  `CODE_SCAN_ALLOW_DECIMAL_QUANTITY` is unsupported and coerced to false.
- SQL-backed concurrent code scan (`MAX_IMAGE_PROCESSING_CONCURRENCY > 1`) is not yet validated
  under real SQL Server; production stays at 1.
- **Follow-up (out of scope here):** the API `asset_progress` is derived only from
  `job.result_json["asset_progress"]` (`_asset_progress_from_job_result` in `api/routes/v3/
  shared.py`). It has no state repository in that builder path, so it cannot fall back to
  `JobAssetProcessingStateRepository.aggregate_progress` when the key is missing. Wiring that
  fallback requires threading a state repo into the response builder and is deferred.
