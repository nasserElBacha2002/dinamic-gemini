# Fase 2 — Contratos backend confirmados

Auditoría contra código real (`backend/src`, `frontend/src/api/assetsApi.ts`). No inventados.

## Auth

Todas las rutas v3 requieren admin auth (`Bearer` + opcional `X-API-Key`).

## `GET /api/v3/config/upload-limits`

Respuesta 200:

```json
{
  "max_files_per_request": 10,
  "max_file_size_bytes": 524288000,
  "max_request_size_bytes": 1073741824,
  "upload_batch_concurrency": 2,
  "retry_attempts": 3,
  "retry_base_delay_ms": 1000
}
```

`upload_batch_concurrency` / retry son **advisory** (cliente).

## `POST /api/v3/inventories/{id}/aisles/{id}/assets`

Multipart (formato web canónico):

| Campo | Forma |
|-------|--------|
| `files` | partes repetidas, una por archivo |
| `upload_batch_id` | un campo texto UUID |
| `client_file_ids` | campos **repetidos** (mismo orden que `files`); también acepta un valor con comas |

Éxito **201** con éxito parcial posible:

```json
{
  "assets": [...],
  "batch_id": "...",
  "uploaded": [{"client_file_id","asset_id","filename","status":"uploaded"}],
  "errors": [{"filename","code","detail","file_index","client_file_id"}]
}
```

Hard fail: 400 demasiados archivos; 422 mismatch/ids inválidos/tamaño spool; 404 aisle; 409 aisle inactiva.  
**No** usa 413/415 en este endpoint (MIME no soportado → soft error en `errors[]`).

Idempotencia: `(aisle_id, upload_batch_id, upload_client_file_id)` cuando ambos ids están presentes.

Upload **permitido** con job activo en el pasillo.

## `GET .../assets`

200: `SourceAssetSummary[]` (`id`, `aisle_id`, `type`, `original_filename`, …). Sin `client_file_id` en listado.

## `DELETE .../assets/{asset_id}`

204 vacío. 409 `AISLE_SOURCE_ASSET_MUTATION_BLOCKED` si job activo (`queued|starting|running|cancel_requested`).

## `POST .../process`

202 `{"job_id":"..."}`. Body opcional provider/model/prompt.  
409 `ACTIVE_JOB_EXISTS` / sin assets / aisle inactiva.

## `GET .../status` / `GET .../jobs`

Status: aisle + `latest_job` + `recent_jobs`.  
Jobs: `{ operational_job_id, jobs: JobSummary[] }`.

Job statuses remotos: `queued|starting|running|cancel_requested|canceled|timed_out|succeeded|failed`.

## Concurrencia de procesamiento

Sin tope global API: un job activo **por pasillo**; pasillos distintos pueden procesar en paralelo.
