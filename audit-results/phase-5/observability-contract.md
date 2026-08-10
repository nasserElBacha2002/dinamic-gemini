# Phase 5 — Observability contract (corrections)

## IDs

- Each HTTP request: unique `X-Request-ID` (echoed).
- Correlation: inbound `X-Correlation-ID` or generated; stored on job `payload_json.correlation_id`.
- Worker: `DINAMIC_CORRELATION_ID` from launch → bootstrap bind.
- Retry/recovery: preserve root correlation; non-HTTP jobs generate their own.

## Metrics

- Single in-process registry; Prometheus text at `GET /metrics`.
- Labels allowlisted; no entity IDs.
- Unmatched routes → `__unmatched__` (never raw path).
- Series budget: `METRICS_MAX_SERIES_PER_METRIC`.
- Histograms: non-cumulative storage; cumulative on render; `le="+Inf"` == `_count`.
- SQL gauges: `OperationalMetricsCollector` TTL cache + single-flight; scrape never hard-fails.

## Auth

- `/metrics`: `METRICS_INTERNAL_AUTH` = `api_key` | `loopback` | `open` (local/test only).
- Phase 4 Model A preserved (no browser API key for scrape).

## Status

Contracts above are **IMPLEMENTED**. Catalog metrics marked `PLANNED` must not be treated as scrape-ready SLIs until producers exist.
