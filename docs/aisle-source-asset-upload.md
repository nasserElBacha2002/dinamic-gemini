# Carga de activos de origen (pasillo)

## Endpoint

`POST /api/v3/inventories/{inventoryId}/aisles/{aisleId}/assets`

Multipart fields:

- `files` — partes de imagen/video
- `upload_batch_id` (opcional) — correlación de la selección del usuario
- `client_file_ids` (opcional, repetido o CSV) — un id por archivo, alineado con `files`

## Límites (por request, no por selección)

| Setting | Default | Descripción |
|---------|--------:|-------------|
| `MAX_FILES_PER_UPLOAD_REQUEST` | 10 | Máximo de archivos por HTTP POST |
| `MAX_UPLOAD_FILE_SIZE_MB` | 25 | Máximo por archivo |
| `MAX_UPLOAD_REQUEST_SIZE_MB` | 100 | Máximo acumulado por POST |

El frontend (`features/uploads`) permite seleccionar **más** de 10 fotos y las divide automáticamente.

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

Un archivo fallido **no** revierte los exitosos. Idempotencia: mismo `(aisle_id, upload_batch_id, upload_client_file_id)` reutiliza el asset existente (migración `0044`).

## Proxy

Ver [UPLOAD-PROXY-LIMITS.md](./UPLOAD-PROXY-LIMITS.md).
