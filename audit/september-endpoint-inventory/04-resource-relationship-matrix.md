# 04 — Resource relationship matrix

## Entidades y vínculos (VERIFIED architecture)

| Parent | Child | Typical path params | Validation mechanism |
|--------|-------|---------------------|----------------------|
| User/Principal | client_id claim | JWT | `get_current_admin` + optional `AUTH_*_CLIENT_ID` |
| Client | Inventory | `inventory_id` | `InventoryAccessPolicy` **when used**; many reads lack it |
| Inventory | Aisle | `inventory_id`,`aisle_id` | `require_aisle_scoped_to_inventory` in some UCs |
| Aisle | Asset / CaptureSession | +`asset_id`/`session_id` | upload scope deps on some routes |
| Aisle | Job | job under aisle process | job repo + aisle linkage |
| Client | Supplier / profiles | `client_id`, supplier ids | clients router JWT; tenant filter **uncertain** |
| Inventory | Export/Import | inventory_id | often JWT only |
| Position labels | Client | client_id, label_id | clients nested router |

## Endpoint coverage of checks

| Check | Endpoints with CONTROL_VERIFIED scope dep | Endpoints POTENTIAL_BOLA |
|-------|------------------------------------------:|-------------------------:|
| Inventory client scope Depends | 33 | 154 |

### CONTROL_VERIFIED examples
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets`
- `DELETE /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/image-display-url`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/labels/batch-render`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}`
- `PATCH /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/ordered-capture-sessions`
- `PUT /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/preliminary-detections/{draft_id}`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/process`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/processing/recover`
- `POST /api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/items`
- `POST /api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/confirm`
- `POST /api/v3/inventories/{inventory_id}/dinamic-scanner-txt-imports/preview`
- `GET /api/v3/inventories/{inventory_id}/labels/{label_id}/download`
- `GET /api/v3/inventories/{inventory_id}/labels/{label_id}/preview`
- `POST /api/v3/inventories/{inventory_id}/labels/{label_id}/render`
- `POST /api/v3/inventories/{inventory_id}/labels/{label_id}/replace`
- `POST /api/v3/inventories/{inventory_id}/local-csv-imports/confirm`
- `POST /api/v3/inventories/{inventory_id}/local-csv-imports/preview`
- `GET /api/v3/inventories/{inventory_id}/local-csv-imports/{import_id}`
- `POST /api/v3/inventories/{inventory_id}/local-inventory-packages/confirm`
- `POST /api/v3/inventories/{inventory_id}/local-inventory-packages/preview`
- `GET /api/v3/inventories/{inventory_id}/local-inventory-packages/{package_id}`
- `GET /api/v3/inventories/{inventory_id}/locations/{location_id}/labels`
- `POST /api/v3/inventories/{inventory_id}/locations/{location_id}/labels`
- `GET /api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}`
- `POST /api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}/invalidate`
- `GET /api/v3/inventories/{inventory_id}/recognition-config`

### Top POTENTIAL_BOLA (CRITICAL DAST)
- `GET /api/v3/clients/` (list_clients)
- `POST /api/v3/clients/` (create_client)
- `GET /api/v3/clients/{client_id}` (get_client)
- `PATCH /api/v3/clients/{client_id}` (update_client)
- `GET /api/v3/inventories/` (list_inventories)
- `GET /api/v3/inventories/{inventory_id}` (get_inventory)
- `PATCH /api/v3/inventories/{inventory_id}` (update_inventory)
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/benchmark/export` (export_aisle_benchmark)
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/code-scans/export` (export_aisle_code_scans)
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/export` (export_aisle_results_csv)
- `GET /api/v3/inventories/{inventory_id}/export` (export_inventory_results)
- `GET /api/v3/inventories/{inventory_id}/export/package` (export_inventory_package_zip)
- `GET /api/v3/inventories/{inventory_id}/export/summary` (export_inventory_summary_csv)
- `GET /api/v3/inventories/{inventory_id}/metrics` (get_inventory_metrics)
- `POST /auth/login` (login) — CRITICAL auth surface; BOLA N/A
