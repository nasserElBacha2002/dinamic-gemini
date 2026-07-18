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

### Evidence & privacy

Per-detection evidence carries `scanner_name`, `scanner_version`, `symbology`,
`bounding_box`, `detection_count`, and `raw_value_hash` (SHA-256 hex). The **raw payload is
never logged** or stored in cleartext in evidence.

## Feature flags (defaults safe)

| Env | Default | Role |
|-----|---------|------|
| `CODE_SCAN_PROCESSING_ENABLED` | false | Master switch for the CODE_SCAN strategy |
| `MAX_IMAGE_PROCESSING_CONCURRENCY` | 1 | ThreadPool workers for SINGLE_ASSET code scan |
| `CODE_SCAN_MAX_IMAGE_SIDE` | 2048 | Downscale before rotated-variant scanning |
| `CODE_SCAN_TIMEOUT_SECONDS` | 15 | Wall-clock budget per image |
| `CODE_SCAN_ENABLE_ROTATIONS` | true | Retry 90/180/270 when 0° finds nothing |
| `CODE_SCAN_ENABLE_PREPROCESSING` | false | Reserved (MVP keeps it off) |
| `CODE_SCAN_MAX_VARIANTS` | 4 | Max scan variants (0/90/180/270) |
| `CODE_SCAN_QUANTITY_MAX` | 99999999 | Max accepted positive-integer quantity |
| `CODE_SCAN_ALLOW_DECIMAL_QUANTITY` | false | MVP rejects decimals |
| `CODE_SCAN_MAX_TECHNICAL_ATTEMPTS` | 2 | Reserved transient-retry budget |

`execution_strategy` is resolved at job start by
`resolve_execution_strategy(effective_mode, pipeline_enabled, code_scan_processing_enabled)`
and snapshotted immutably on the job.

## Migrations

- `0053_code_scan_processing_strategy.sql` — widens the `inventory_jobs.execution_strategy`
  CHECK to include `CODE_SCAN` (drop/recreate, idempotent) and adds the optional
  `job_asset_code_scan_detections` audit table. The sync-API `aisle_code_scan_detections`
  table is left untouched. Mirrored in `schema.sql`.

## Deployment

`Dockerfile.worker` now installs `libzbar0` and verifies `pyzbar` importability at build
time (previously API-only). Without it, code scan surfaces `FAILED_TECHNICAL` per asset.

## Limitations (explicit)

- **No OCR and no LLM fallback**: if the label has no machine-readable QR/CODE128 the asset
  is `UNRECOGNIZED` (never sent to an LLM).
- Timeout is enforced between scan variants (wall-clock), not inside a single decode call.
- `CODE_SCAN_ENABLE_PREPROCESSING` and `CODE_SCAN_MAX_TECHNICAL_ATTEMPTS` are wired as config
  but the MVP does not add preprocessing filters or transient-retry loops.
