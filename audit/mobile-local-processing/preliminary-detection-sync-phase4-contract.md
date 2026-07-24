# Phase 4 — Preliminary detection sync — contract

## Request

`PUT /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}`

```json
{
  "schema_version": "1",
  "capture_session_id": "uuid-local",
  "capture_photo_id": "uuid-local",
  "client_file_id": "uuid",
  "asset_id": "uuid-remoto",
  "processing_mode": "CODE_SCAN",
  "status": "RESOLVED",
  "internal_code": "ABC123",
  "quantity": 10,
  "quantity_status": "PRESENT",
  "detected_format": "PIPE",
  "detected_symbology": "QR_CODE",
  "candidate_count": 1,
  "parser_version": "1.1.0",
  "detector_version": "mlkit-barcode-1.0.0",
  "prepared_asset_sha256": "sha256:<64 hex>",
  "payload_hash": "sha256:<64 hex>",
  "processing_ms": 120,
  "detected_at": "2026-07-24T12:00:00Z"
}
```

### Forbidden in payload

- raw barcode payload / preview
- image bytes
- local file paths
- tokens
- authoritative `company_id` / `inventory_id` / `aisle_id`
- final position / reviewed status

## Success response (200)

```json
{
  "draft_id": "uuid",
  "server_preliminary_id": "uuid",
  "status": "VALIDATED",
  "received_at": "2026-07-24T12:00:01Z",
  "validation_errors": [],
  "duplicate": false
}
```

## Error mapping

| Condition | HTTP | Client sync status |
|-----------|------|--------------------|
| Ingest flag off | 404 | retry / feature unavailable window |
| Validation failed | 422 | REJECTED |
| draft_id content conflict | 409 | CONFLICT |
| Asset missing / aisle mismatch | 404 body `PENDING_ASSET` | RETRY_SCHEDULED |
| Forbidden | 403 | FAILED_TERMINAL |
| Network / 429 / 5xx | as returned | RETRY_SCHEDULED |

## Coherence rules (server)

- `RESOLVED` → `internal_code` required
- `UNRESOLVED` / `NOT_APPLICABLE` → `internal_code` must be null
- `AMBIGUOUS` → quantity must be null
- `quantity_status=PRESENT` → quantity required (1..max)
- `quantity_status=MISSING|INVALID` → quantity null
- SHA-256 must match `sha256:[0-9a-f]{64}`
- `processing_mode` must be `CODE_SCAN`

## Idempotency keys

1. `draft_id` (primary)
2. `(client_file_id, detector_version, parser_version, prepared_asset_sha256)`
