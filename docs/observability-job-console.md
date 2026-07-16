# Observability — job artifacts, retry chain, logs, timeline

## Preserved contracts

- Existing job detail, full `execution-log`, `execution-log.txt`, `hybrid-report`, `traceability`, `auditability`, cancel, and retry routes remain unchanged.
- Retry continues to create a new `job_id` linked by `retry_of_job_id`.
- Platform admins with `client_id=null` keep single-tenant access; company-scoped JWTs (`AUTH_ADMIN_CLIENT_ID` / `AUTH_JAIRO_CLIENT_ID`) enforce inventory `client_id` match (404 on mismatch).

## New endpoints (inventory-scoped)

| Method | Path | Notes |
|--------|------|--------|
| GET | `.../jobs/{job_id}/artifacts` | Catalog (no `storage_key`) |
| GET | `.../jobs/{job_id}/artifacts/{artifact_id}` | Metadata |
| GET | `.../jobs/{job_id}/artifacts/{artifact_id}/download` | Authz + namespace check |
| GET | `.../jobs/{job_id}/artifacts/{artifact_id}/preview` | Truncated text/JSON |
| GET | `.../jobs/{job_id}/retry-chain` | Linear retry attempts |
| GET | `.../jobs/{job_id}/execution-log/page` | Cursor pagination (legacy full log kept) |
| GET | `.../jobs/{job_id}/timeline` | Derived structured events from JSONL |
| GET | `.../jobs/{job_id}/errors` | Structured errors |

## Config

See `.env.example` (`OBSERVABILITY_*`, `AUTH_*_CLIENT_ID`).

## Residual gaps (not in this slice)

- Dedicated timeline DB table + idempotent pipeline emitters for all event types
- Retention cleanup job / reconciliation admin command
- Full operator vs company-admin UI permission matrix beyond JWT role + prompt redaction
- Incremental JSONL offset index for multi-GB logs
- Full E2E cases A–F automation
