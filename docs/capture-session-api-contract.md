# Capture Session API Contract (v3)

Documento de contrato para frontend y producto del módulo de ingesta de medios.  
Fuente de verdad: rutas en `backend/src/api/routes/v3/capture_sessions.py` + schemas en `backend/src/api/schemas/capture_schemas.py`.

## Convenciones

- Base path: `/api/v3/inventories`
- Todas las respuestas de negocio mapeadas usan formato estructurado:
  - `{"code": "<ERROR_CODE>", "detail": "<texto>"}`
- Fechas en respuesta: ISO-8601 UTC serializada por FastAPI.
- Entidad técnica: `CaptureSession` (UX: Import Session).

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

## 6) Subir items a staging

- **POST** `/{inventory_id}/aisles/{aisle_id}/capture-sessions/{session_id}/items`
- **Body:** `multipart/form-data` (`files[]`)
- **Respuesta 201:** `UploadCaptureSessionItemsResponse`
- **Estado requerido:**
  - sesión no cerrada (`closed_at is null`)
  - no `CANCELLED`, `FAILED`, `CONFIRMED`
- **Errores principales:**
  - `CAPTURE_SESSION_NOT_FOUND` (404)
  - `CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS` (409)
  - `CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT` (409)
  - `EMPTY_UPLOAD` (422)
  - `ZERO_BYTE_FILE` (422)
  - `CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE` (422)
  - `CAPTURE_SESSION_STAGING_FILE_TOO_LARGE` (422)
  - `UNSUPPORTED_ASSET_TYPE` (400)

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
