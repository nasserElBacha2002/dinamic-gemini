# Capture Session API Contract (v3)

Documento de contrato para frontend y producto del módulo de ingesta de medios.  
Fuente de verdad: rutas en `backend/src/api/routes/v3/capture_sessions.py` + schemas en `backend/src/api/schemas/capture_schemas.py`.

## Convenciones

- Base path: `/api/v3/inventories`
- Todas las respuestas de negocio mapeadas usan formato estructurado:
  - `{"code": "<ERROR_CODE>", "detail": "<texto>"}`
- Fechas en respuesta: ISO-8601 UTC serializada por FastAPI.
- Entidad técnica: `CaptureSession` (UX: Import Session).
- Referencia primaria frontend para contratos TS: `frontend/src/types/captureSession.ts`.

## Modelos de respuesta

### CaptureSessionResponse

- `id: string`
- `inventory_id: string`
- `aisle_id: string`
- `status: string`
- `created_at: string(datetime)`
- `updated_at: string(datetime)`
- `opened_at?: string(datetime) | null`
- `closed_at?: string(datetime) | null`
- `clock_offset_seconds: number`

### CaptureSessionItemResponse

- `id: string`
- `session_id: string`
- `staging_storage_key: string`
- `import_status: "pending_import" | "importing" | "imported" | "import_failed"`
- `assignment_status: "pending" | "proposed" | "conflict" | "unassigned"`
- `content_hash?: string | null`
- `effective_capture_time?: string(datetime) | null`
- `time_source?: "exif" | "file_mtime" | "fallback_clock" | null`
- `time_confidence?: number | null`
- `adjusted_capture_time?: string(datetime) | null`
- `assignment_reason?: string | null`
- `preview_target_position_id?: string | null`
- `linked_source_asset_id?: string | null`
- `last_error_code?: string | null`
- `last_error_detail?: string | null`
- `original_filename?: string | null`
- `updated_at: string(datetime)`

### CaptureSessionDetailResponse

- `session: CaptureSessionResponse`
- `items: CaptureSessionItemResponse[]`

### MaterializeCaptureSessionResponse

- `session: CaptureSessionResponse`
- `items: CaptureSessionItemResponse[]`
- `created_assets_count: number`

### CaptureSessionStagingUploadFileError

- `filename: string`
- `code: string` (estable; alineado con códigos v3 e.g. `ZERO_BYTE_FILE`, `UNSUPPORTED_ASSET_TYPE`, `CAPTURE_SESSION_STAGING_FILE_TOO_LARGE`, `CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT`)
- `detail: string`
- `file_index: number` (índice 0-based del archivo en el multipart **de ese** POST)

### UploadCaptureSessionItemsResponse

- `items: CaptureSessionItemResponse[]` — filas persistidas por esta petición (importadas y, si aplica, filas `import_failed` por fallos de almacenamiento/persistencia)
- `errors: CaptureSessionStagingUploadFileError[]` — fallos de **validación / negocio por archivo** sin fila correspondiente (o duplicado detectado al guardar sin persistir ítem importado)

## Política de errores (staging batch)

- **Errores globales de la petición** (request inválido o sesión no acepta uploads): el servidor responde con **HTTP de error** (4xx/5xx) y cuerpo de error estructurado o validación FastAPI según el caso. Ejemplos: `EMPTY_UPLOAD` (422), `CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE` (422), `CAPTURE_SESSION_NOT_FOUND` (404), `CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS` (409).
- **Errores por archivo dentro de un multipart válido** (tamaño de lote OK, sesión acepta uploads): el servidor responde **201** con `items` y `errors` poblados según corresponda (**éxito parcial** permitido: algunos archivos importados, otros listados solo en `errors[]`).

## Frontend (ingesta — workspace de upload)

- El cliente agrupa archivos en tandas de hasta el máximo por POST (config backend `v3_capture_max_files_per_upload`, por defecto 50) y envía **varias peticiones secuenciales** (una tanda tras otra), no POSTs en paralelo por tanda. Ver comentarios en `frontend/src/features/ingestionSessions/hooks/useUploadCaptureItems.ts` y `captureSessionsApi.ts`.

## Endpoints

## 1) Crear sesión

- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions`
- **Body:** ninguno
- **Respuesta 201:** `CaptureSessionResponse`
- **Precondición de estado:** no hay sesión abierta excediendo política de concurrencia.
- **Errores principales:**
  - `INVENTORY_NOT_FOUND` (404)
  - `AISLE_NOT_FOUND` (404)
  - `OPEN_CAPTURE_SESSION_EXISTS` (409)

## 2) Cerrar sesión

- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/close`
- **Body:** ninguno
- **Respuesta 200:** `CaptureSessionDetailResponse`
- **Estado requerido:**
  - permitido en `DRAFT` (si tiene >=1 item `IMPORTED`)
  - permitido en `IMPORTING`
  - idempotente en `READY_FOR_REVIEW` (si ya cerrada)
- **Errores principales:**
  - `CAPTURE_SESSION_NOT_FOUND` (404)
  - `CAPTURE_SESSION_INVALID_STATE` (409)

## 3) Cancelar sesión

- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/cancel`
- **Body:** ninguno
- **Respuesta 200:** `CaptureSessionDetailResponse`
- **Estado requerido:**
  - permitido en estados no terminales y `CANCELLED` (idempotente)
  - prohibido en `CONFIRMED`
- **Errores principales:**
  - `CAPTURE_SESSION_NOT_FOUND` (404)
  - `CAPTURE_SESSION_INVALID_STATE` (409)

## 4) Listar sesiones

- **GET** `/{inventory_id}/capture-sessions`
- **Query opcional:**
  - `aisle_id`
  - `status` (csv)
  - `created_from`
  - `created_to`
  - `page` (>=1)
  - `page_size` (>=1)
- **Respuesta 200:** `PaginatedCaptureSessionListResponse`
- **Errores principales:**
  - `INVENTORY_NOT_FOUND` (404)
  - `CAPTURE_SESSION_STATUS_FILTER_INVALID` (422)

## 5) Detalle de sesión

- **GET** `/{inventory_id}/capture-sessions/{session_id}`
- **Respuesta 200:** `CaptureSessionDetailResponse`
- **Errores principales:**
  - `INVENTORY_NOT_FOUND` (404)
  - `CAPTURE_SESSION_NOT_FOUND` (404)

## 6) Subir items a staging (batch multipart)

Dos rutas equivalentes (misma forma de body y de respuesta 201):

- **POST** `/{inventory_id}/capture-sessions/{session_id}/items` (sesión a nivel inventario; `aisle_id` de la sesión puede ser `null`)
- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items` (compatibilidad con sesión vinculada a pasillo)

**Body:** `multipart/form-data` con uno o más campos de archivo bajo el nombre `files` (múltiples partes `files` en la misma petición).

**Respuesta 201:** `UploadCaptureSessionItemsResponse`

- `items[]`: ítems persistidos en esta petición (p. ej. `import_status: imported`, o `import_failed` si falló escritura en almacenamiento/persistencia tras validar el archivo).
- `errors[]`: fallos **por archivo** (validación, duplicado de contenido en la sesión, etc.) con `filename`, `code`, `detail`, `file_index`. Un mismo POST puede terminar en **éxito parcial**: algunos archivos en `items`, otros solo en `errors`.

**Estado requerido de la sesión:**

- no cerrada (`closed_at is null`)
- no `CANCELLED`, `FAILED`, `CONFIRMED`

**Errores HTTP de toda la petición (sin cuerpo 201 de batch):**

- `CAPTURE_SESSION_NOT_FOUND` (404)
- `CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS` (409)
- `EMPTY_UPLOAD` (422) — ningún archivo
- `CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE` (422) — más archivos que el máximo por POST

**Nota:** códigos como `ZERO_BYTE_FILE`, `UNSUPPORTED_ASSET_TYPE`, `CAPTURE_SESSION_STAGING_FILE_TOO_LARGE` o `CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT` pueden aparecer **dentro de** `errors[]` con **201** cuando el resto del batch es procesable. No deben confundirse con los mismos códigos devueltos como error HTTP global en otros flujos de la API.

## 7) Actualizar clock offset

- **PATCH** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/clock-offset`
- **Body JSON:**
  - `clock_offset_seconds: number`
- **Respuesta 200:** `CaptureSessionDetailResponse`
- **Estado requerido:**
  - no `CANCELLED`, `FAILED`, `CONFIRMED`, `CONFIRMING`
  - si está en `ASSIGNMENT_PROPOSED`, resetea a `READY_FOR_REVIEW` y limpia preview de items importados
- **Errores principales:**
  - `CAPTURE_SESSION_NOT_FOUND` (404)
  - `CAPTURE_SESSION_INVALID_CLOCK_OFFSET` (422)
  - `CAPTURE_SESSION_INVALID_STATE` (409)

## 8) Ejecutar preview de asignación

- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/preview-assignment`
- **Body:** ninguno
- **Respuesta 200:** `CaptureSessionDetailResponse`
- **Estado requerido:**
  - `READY_FOR_REVIEW` o `ASSIGNMENT_PROPOSED`
  - sesión cerrada (`closed_at != null`)
- **Errores principales:**
  - `CAPTURE_SESSION_NOT_FOUND` (404)
  - `CAPTURE_SESSION_PREVIEW_NOT_ALLOWED` (409)

## 9) Materializar a SourceAsset

- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/materialize`
- **Body JSON:**
  - `idempotency_key: string (1..255)`
- **Respuesta 200:** `MaterializeCaptureSessionResponse`
- **Estado requerido:**
  - `ASSIGNMENT_PROPOSED`
  - items importados deben estar en `PROPOSED`
  - no debe haber `linked_source_asset_id` previos
- **Errores principales:**
  - `CAPTURE_SESSION_NOT_FOUND` (404)
  - `CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY` (422)
  - `CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED` (409)
  - `CAPTURE_SESSION_ALREADY_MATERIALIZED` (409)
  - `CAPTURE_SESSION_MATERIALIZATION_FAILED` (500)

## Nota de invariantes

- Upload a `items` **no** crea `SourceAsset`.
- Solo `materialize` crea `SourceAsset`.
- `process_aisle` opera exclusivamente sobre `SourceAsset`.
