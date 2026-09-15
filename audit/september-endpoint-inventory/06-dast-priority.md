# 06 — DAST priority ranking

## CRITICAL (15)
1. `EP-0013` GET `/api/v3/clients/` — list_clients
1. `EP-0014` POST `/api/v3/clients/` — create_client
1. `EP-0015` GET `/api/v3/clients/{client_id}` — get_client
1. `EP-0016` PATCH `/api/v3/clients/{client_id}` — update_client
1. `EP-0055` GET `/api/v3/inventories/` — list_inventories
1. `EP-0061` GET `/api/v3/inventories/{inventory_id}` — get_inventory
1. `EP-0062` PATCH `/api/v3/inventories/{inventory_id}` — update_inventory
1. `EP-0078` GET `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export` — export_aisle_benchmark
1. `EP-0087` GET `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export` — export_aisle_code_scans
1. `EP-0094` GET `/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export` — export_aisle_results_csv
1. `EP-0178` GET `/api/v3/inventories/{inventory_id}/export` — export_inventory_results
1. `EP-0179` GET `/api/v3/inventories/{inventory_id}/export/package` — export_inventory_package_zip
1. `EP-0180` GET `/api/v3/inventories/{inventory_id}/export/summary` — export_inventory_summary_csv
1. `EP-0204` GET `/api/v3/inventories/{inventory_id}/metrics` — get_inventory_metrics
1. `EP-0208` POST `/auth/login` — login

## HIGH (count=161) — categories
- Uploads/imports/downloads: 16
- Admin: 4
- Jobs/processing: 21
- Other POTENTIAL_BOLA nested resources: remainder

## Priority rationale
1. Authentication (`/auth/login`)
2. Horizontal/tenant IDOR on list/get/export
3. Admin surfaces
4. File upload / TXT / ZIP / CSV
5. Processing jobs (cost/CPU)
6. Public docs/metrics
