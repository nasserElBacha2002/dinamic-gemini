# Phase 5 — Dashboard specification

## API

- request rate (`http_requests_total`)
- error rate by `status_class`
- latency p95/p99 (`http_request_duration_seconds`)
- readiness probe success

## Jobs

- throughput completed/failed/canceled/stale
- queue wait / processing duration (when instrumented)
- `jobs_in_state` gauges
- stale / expired leases

## Workers

- `worker_process_up`
- heartbeat age
- jobs started/completed/failed/abort

## Providers

- request rate / error / timeout by `provider`
- latency histogram

## Storage / artifacts

- publication success/fail
- outbox pending/failed
- publication latency

Panels must map to an alert or runbook action — no vanity charts.
