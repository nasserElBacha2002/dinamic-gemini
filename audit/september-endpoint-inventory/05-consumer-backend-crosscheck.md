# 05 — Consumer ↔ backend crosscheck

Heurística: literales `/api/v3...` y `/auth...` en `frontend/src` y `mobile/src` (+ tests).

| Status | Count |
|--------|------:|
| REGISTERED_AND_USED (FE or mobile or tests signal) | 126 |
| REGISTERED_NOT_USED (no literal match) | 96 |
| used_by_frontend | 17 |
| used_by_mobile | 35 |

## Notes

- **USED_NOT_REGISTERED**: no demostrado en esta pasada (no se halló cliente llamando paths fuera del registro introspectado).
- Prefijo canónico: `/api/v3` + `/auth`. No hay `/api/v2` montado (VERIFIED `server.py` comment legacy removed).
- FE puede construir paths por concatenación → falsos `REGISTERED_NOT_USED`.
- Mobile authoritative sync / capture usa subset de inventories/aisles/assets/capture.

## Sample REGISTERED_NOT_USED (first 25)
- `GET /api/v3/analytics/aisles`
- `GET /api/v3/analytics/quality`
- `GET /api/v3/analytics/trends`
- `POST /api/v3/clients/{client_id}/position-labels/marker-set`
- `GET /api/v3/clients/{client_id}/position-labels/{label_id}/download`
- `POST /api/v3/clients/{client_id}/position-labels/{label_id}/invalidate`
- `GET /api/v3/clients/{client_id}/position-labels/{label_id}/preview`
- `POST /api/v3/clients/{client_id}/position-labels/{label_id}/render`
- `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles`
- `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/active`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/clone`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/test-code`
- `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/versions/{version}`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/extraction-profiles/{profile_id}/activate`
- `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/label-profiles`
- `PUT /api/v3/clients/{client_id}/suppliers/{supplier_id}/label-profiles/{label_kind}`
- `POST /api/v3/clients/{client_id}/suppliers/{supplier_id}/prompt-configs/{config_id}/activate`
- `GET /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations`
- `PUT /api/v3/clients/{client_id}/suppliers/{supplier_id}/reference-images/{image_id}/annotations`
- `POST /api/v3/inventories/bulk-soft-delete`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/activate`
- `PUT /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-code-scan`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/authoritative-exclusion`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/authoritative-readiness`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/deactivate`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/finalize-authoritative`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/download`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/artifacts/{artifact_id}/preview`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/processing`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/invalidate-result`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-detail`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/processing-events/export`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/reprocess`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/retry-persistence`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/assets/{asset_id}/send-to-external`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/errors`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/execution-log/page`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/retry-chain`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/jobs/{job_id}/timeline`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/labels/batch-render`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}`
- `PATCH /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/locations/{location_id}`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-operational-view`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-sequence`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positioning-warnings`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/by-position`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/merge`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-capabilities`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revision-history`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/apply`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/cancel`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/diff`
- `PUT /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/revisions/{revision_id}/items/{asset_id}`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/rollback`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess-capabilities`
- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/adopt`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/cancel`
- `POST /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/server-reprocess/{run_id}/execute`
- `POST /api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/materialize`
- `POST /api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/materialize`
- `POST /api/v3/inventories/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/preview`
- `GET /api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation`
- `POST /api/v3/inventories/{inventory_id}/jobs/{job_id}/position-reconciliation/retry`
- `GET /api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-history`
- `POST /api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override`
- `POST /api/v3/inventories/{inventory_id}/jobs/{job_id}/results/{result_id}/position-override/restore`
- `GET /api/v3/inventories/{inventory_id}/jobs/{job_id}/source-assets/{asset_id}/position-detections`
- `GET /api/v3/inventories/{inventory_id}/jobs/{job_id}/unassigned-results`
- `GET /api/v3/inventories/{inventory_id}/labels/{label_id}/download`
- `GET /api/v3/inventories/{inventory_id}/labels/{label_id}/preview`
- `POST /api/v3/inventories/{inventory_id}/labels/{label_id}/render`
- `POST /api/v3/inventories/{inventory_id}/labels/{label_id}/replace`
- `POST /api/v3/inventories/{inventory_id}/local-csv-imports/confirm`
- `POST /api/v3/inventories/{inventory_id}/local-inventory-packages/confirm`
- `GET /api/v3/inventories/{inventory_id}/locations/{location_id}/labels`
- `POST /api/v3/inventories/{inventory_id}/locations/{location_id}/labels`
- `GET /api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}`
- `POST /api/v3/inventories/{inventory_id}/locations/{location_id}/labels/{label_id}/invalidate`
- `GET /docs`
- `HEAD /docs`
- `GET /docs/oauth2-redirect`
- `HEAD /docs/oauth2-redirect`
- `GET /openapi.json`
- `HEAD /openapi.json`
- `GET /redoc`
- `HEAD /redoc`
