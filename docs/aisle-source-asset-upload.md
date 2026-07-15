# Carga de activos de origen (pasillo)

## Endpoint

`POST /api/v3/inventories/{inventoryId}/aisles/{aisleId}/assets`

Multipart fields:

- `files` — partes de imagen/video
- `upload_batch_id` (opcional) — correlación de la selección del usuario; si se envía debe tener
  forma de UUID (≤ 64 caracteres) o la request se rechaza con 422.
- `client_file_ids` (opcional, repetido o CSV) — un id por archivo, alineado con `files`. Si se
  envía, su longitud **debe** coincidir exactamente con la cantidad de archivos usables del
  request (422 `CLIENT_FILE_IDS_MISMATCH` en caso contrario; no se rellena en silencio con
  `null`). Cada id no vacío debe tener forma de UUID (422 `CLIENT_FILE_ID_INVALID`).

## Límites (por request, no por selección)

| Setting | Default | Descripción |
|---------|--------:|-------------|
| `MAX_FILES_PER_UPLOAD_REQUEST` | 10 | Máximo de archivos por HTTP POST |
| `MAX_UPLOAD_FILE_SIZE_MB` | 500 (histórico; alias legacy `MAX_UPLOAD_SIZE_MB`) | Máximo por archivo |
| `MAX_UPLOAD_REQUEST_SIZE_MB` | 1024 (debe ser ≥ al límite por archivo) | Máximo acumulado por POST |

El frontend (`features/uploads`) permite seleccionar **más** de 10 fotos y las divide
automáticamente, y puede leer estos límites en runtime vía `GET /api/v3/config/upload-limits`
en lugar de hardcodearlos.

Los defaults **500 / 1024** son de compatibilidad histórica. Para una carga típica de fotos
ver configuración recomendada en [`docs/deployment/UPLOAD-PROXY-LIMITS.md`](../deployment/UPLOAD-PROXY-LIMITS.md)
(p. ej. 50 MB / archivo, 250 MB / request). `retry_attempts` en el endpoint = reintentos
**adicionales** tras el primer intento.

## Respuesta parcial (HTTP 201)

```json
{
  "assets": [ /* SourceAssetResponse[] — compatibilidad */ ],
  "batch_id": "uuid",
  "uploaded": [
    { "client_file_id": "uuid", "asset_id": "uuid", "filename": "a.jpg", "status": "uploaded" }
  ],
  "errors": [
    { "client_file_id": "uuid", "filename": "b.jpg", "file_index": 1, "code": "...", "detail": "..." }
  ]
}
```

Un archivo fallido **no** revierte los exitosos. Idempotencia: mismo `(aisle_id, upload_batch_id, upload_client_file_id)` reutiliza el asset existente (migración `0044`, índice único
`UQ_source_assets_aisle_upload_batch_client`). Si dos requests concurrentes suben el mismo
`client_file_id` a la vez, el segundo insert pierde la carrera en base de datos: el blob
duplicado se borra y la respuesta devuelve el asset ganador como si fuera exitoso (no se reporta
como error). Otros errores de base de datos siguen siendo errores reales (`ASSET_PERSIST_FAILED`,
sin exponer el mensaje interno de la excepción). Si el pasillo falla al finalizar/reconciliar
después de persistir los assets, estos **no** se pierden ni se reportan como fallo global; el
error de reconciliación solo se registra en logs.

## Proxy

Ver [UPLOAD-PROXY-LIMITS.md](./UPLOAD-PROXY-LIMITS.md).
