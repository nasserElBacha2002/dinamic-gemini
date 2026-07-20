# ProcessingEvent observability semantics

**Decision:** ProcessingEvent is **A — best-effort telemetry**, not durable transactional audit.

## Rules

1. Publish failures must not fail OCR / code-scan asset processing.
2. Failed publishes increment structured metric `processing_event_publish_failed_total`.
3. Results / finalize metadata may set `observability_incomplete=true`.
4. Do not use the event log as commit evidence; job / attempt / asset state is authoritative.
5. At most one `asset.finalized` per strategy `process()` call (guarded).
6. Never publish OCR full text; metadata goes through `sanitize_metadata`.
7. `ocr.candidate_rejected` is aggregated (+ configurable sample), not one event per rejection.

## Event order (INTERNAL_OCR, happy path)

1. `asset.source_loaded`
2. label detection events (optional)
3. per-variant: tokens / anchors / candidates / (aggregated rejections) / variant_completed|failed
4. candidate mapping + profile validation events (when enabled)
5. `asset.finalized` (exactly once)

## Consistency invariants (worker)

- Attempt terminal state and per-asset results must agree for reported job success.
- Do not mark job SUCCEEDED if aisle is FAILED.
- Do not finalize the same asset twice for the same attempt (CAS / row version preferred over process memory).
- Fallback external must be idempotent per asset.
- `result_json` partial writes must not be advertised as complete.
