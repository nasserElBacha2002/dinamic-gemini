# Phase 5 — Observability contract

## Goals

- Detect failures before user impact.
- Correlate API → job → worker without high-cardinality metric labels.
- Scrapeable metrics + protected `/metrics`.
- Stale-fail recovery remains Phase 3 policy (no lease stealing).

## IDs

| ID | Where | Metric label? |
| -- | ----- | ------------- |
| `request_id` | HTTP header `X-Request-ID`, logs, response | No |
| `correlation_id` | HTTP header `X-Correlation-ID`, logs, job context | No |
| `job_id` / `execution_id` | Logs only | **Never** |
| `aisle_id` / `inventory_id` | Logs only | **Never** |

## Metric label allowlist

`component`, `operation`, `outcome`, `status`, `job_type`, `provider`, `stage`, `reason_code`, `environment`, `repository_backend`, `method`, `route_template`, `status_class`, `reason`, `artifact_kind`, `storage_backend`, `worker_role`, `host_group`, `error_class`, `failure_code`.

## Endpoints

| Path | Role | Auth |
| ---- | ---- | ---- |
| `/health` | Liveness | Public |
| `/ready` | Readiness (schema + repository backend) | Public |
| `/metrics` | Prometheus text | `METRICS_INTERNAL_AUTH` (api_key / loopback / open-local) |
| `/api/v3/observability/metrics` | Product H5 JSON aggregates | Admin JWT (unchanged) |

## Registry

Single process registry: `src.observability.metrics.registry.get_metrics_registry()`.
Lease counters from Phase 3 delegate into the same registry.

## OpenTelemetry

Not introduced as a mandatory migration. Interfaces remain compatible for a future exporter.
