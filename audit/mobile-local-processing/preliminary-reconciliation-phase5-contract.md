# Preliminary reconciliation — Phase 5 contract

## Authority

```text
local = candidate
remote = authority
reconciliation = diagnostic evidence
```

Reconciliation never mutates positions, jobs, `/process`, OCR, or fallback.

## Comparison version

`comparison_version = "1"` (constant `COMPARISON_VERSION`).

Idempotency key: `(preliminary_detection_id, comparison_version)`.

## Outcomes

| Outcome | Meaning |
|---------|---------|
| `MATCH_CODE_AND_QUANTITY` | Codes equal, quantities equal |
| `MATCH_CODE_BOTH_QUANTITY_MISSING` | Codes equal, both qty null |
| `MATCH_CODE_LOCAL_QUANTITY_MISSING` | Codes equal, local qty null |
| `MATCH_CODE_REMOTE_QUANTITY_MISSING` | Codes equal, remote qty null |
| `MATCH_CODE_QUANTITY_DIFFERENT` | Codes equal, qty differ |
| `CODE_MISMATCH` | Both resolved, codes differ |
| `LOCAL_ONLY` | Local code, remote unresolved |
| `REMOTE_ONLY` | Remote code, local unresolved |
| `BOTH_UNRESOLVED` | Neither has code |
| `LOCAL_AMBIGUOUS` / `REMOTE_AMBIGUOUS` / `BOTH_AMBIGUOUS` | Ambiguity |
| `NOT_COMPARABLE` | See reason field |

## Reconciliation status

`PENDING` | `RUNNING` | `COMPLETED` | `NOT_COMPARABLE` | `RETRY_SCHEDULED` | `FAILED_TERMINAL`

(Current use case writes `COMPLETED`, `NOT_COMPARABLE`, `RETRY_SCHEDULED`.)

## Endpoints

### Trigger (idempotent batch)

`POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/reconcile-preliminary-detections`

Body: `{ "job_id": "...", "batch_limit": 50 }`

### List (read-only)

`GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-reconciliations`

Query: `outcome`, `asset_id`, `client_file_id`, `parser_version`, `detector_version`, `comparable`, `compared_after`, `compared_before`, `limit`, `offset`

Response includes `metrics` and `authority_notice`.

## Feature flags

| Flag | Env / mobile | Default |
|------|----------------|---------|
| Server reconcile | `SERVER_PRELIMINARY_RECONCILIATION` | false |
| Metrics log | `PRELIMINARY_RECONCILIATION_METRICS` | false |
| Mobile view | `mobilePreliminaryReconciliationView` / `DINAMIC_FLAG_PRELIMINARY_RECONCILIATION_VIEW` | false |

## Versions recorded

Local: parser, detector. Remote: pipeline/prompt version when available. App/device: not persisted in table (follow-up).
