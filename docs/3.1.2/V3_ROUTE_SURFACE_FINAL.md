# V3 Route Surface (Final — Stage 3)

Single supported API surface for the active inventory workflow. All routes are under `/api/v3/inventories`.

## Module layout

| Module | Path prefix | Responsibility |
|--------|-------------|----------------|
| `src.api.routes.v3` | `/api/v3/inventories` | Main router; includes all sub-routers |
| `v3.inventories` | (same) | POST/GET /, GET /{id}, GET /{id}/metrics |
| `v3.aisles` | (same) | POST/GET /{inv}/aisles, POST .../process, GET .../status, GET .../jobs/{jid}/execution-log |
| `v3.assets` | (same) | POST/GET .../aisles/{aid}/assets, GET .../assets/{asset_id}/file |
| `v3.positions` | (same) | GET .../aisles/{aid}/positions, GET .../positions/{pid} |
| `v3.reviews` | (same) | POST .../positions/{pid}/reviews |
| `v3.shared` | — | Response mappers, exception mapping, HEIC normalized path resolution |

## Route list

- `POST /api/v3/inventories/` — create inventory  
- `GET /api/v3/inventories/` — list inventories  
- `GET /api/v3/inventories/{inventory_id}` — get inventory  
- `GET /api/v3/inventories/{inventory_id}/metrics` — inventory metrics  
- `POST /api/v3/inventories/{inventory_id}/aisles` — create aisle  
- `GET /api/v3/inventories/{inventory_id}/aisles` — list aisles (with latest job)  
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process` — start aisle processing (202)  
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/status` — aisle status  
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log` — job execution log  
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` — upload assets  
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets` — list assets  
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file` — asset file (or HEIC preview)  
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions` — list positions  
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}` — position detail  
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}/reviews` — submit review action  

## Removed in Stage 3

- `/api/v1/inventory/jobs` (all: create, status, result, report, artifacts)  
- `/api/v1/inventory/jobs/{job_id}/entities` and entity evidence/review/audit  

Replaced by: v3 process/status/positions/position detail/reviews.
