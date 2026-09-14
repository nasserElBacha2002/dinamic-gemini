# 10 — Unmounted and legacy routes

## Mounted (VERIFIED `server.py`)

- `v3_router` → prefix `/api/v3/inventories` + nested routers
- `v3_clients_router` → `/api/v3/clients`
- `v3_analytics_router` → `/api/v3/analytics`
- `v3_review_queue_router` → `/api/v3/review-queue`
- `v3_observability_router` → `/api/v3/observability`
- `v3_config_router` → `/api/v3/config`
- `auth_router` → `/auth`
- `v3_admin_ai_config_router`, `v3_admin_storage_router`, `v3_admin_finalization_recovery_router` → `/api/v3/admin/...`
- App-level: `/health`, `/ready`, `/metrics`
- Built-in: `/docs`, `/redoc`, `/openapi.json`

## Nested under inventories router (`routes/v3/router.py`)

inventories, local_csv_imports, local_inventory_packages, dinamic_scanner_txt_imports, capture_sessions, ordered_capture, aisle_locations, aisles, code_scans, assets, authoritative_local_code_scan, authoritative_aisle_finalization, server_reprocess, aisle_revisions, preliminary_detections, preliminary_reconciliations, positions, position_label_detections, position_overrides, position_reconciliation, positioning_operational, image_results, processing_observability, reviews.

## Legacy / notes

- Legacy v1 jobs/entities **removed** (comment in `server.py`).
- `job_observability.py` documents handlers possibly wired via other modules — verify no duplicate mount (handlers live under aisles/processing_observability).
- No WebSocket/SSE/GraphQL/gRPC routes detected in FastAPI app.
- Workers: no HTTP server (`run_worker` process) — NOT_APPLICABLE as HTTP surface.

## Conditional

- `/metrics` may 404 if metrics disabled; auth via `metrics_access_allowed` (API key / mode).
- API key middleware only if `API_KEY` + prefixes configured.
