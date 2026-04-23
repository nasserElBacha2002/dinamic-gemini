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
- `group_id?: string | null` — G3: id del grupo temporal asignado por `compute-groups`; `null` si aún no se agrupó o el ítem no fue elegible
- `updated_at: string(datetime)`

### CaptureSessionDetailResponse

- `session: CaptureSessionResponse`
- `items: CaptureSessionItemResponse[]`

### CaptureSessionGroupSummaryResponse (G3 + G4)

- `group_id: string`
- `group_index: number` (1-based, estable por recomputo dentro de la sesión)
- `item_count: number`
- `start_time: string(datetime)` — mínimo de `COALESCE(adjusted_capture_time, effective_capture_time)` entre miembros
- `end_time: string(datetime)` — máximo de la misma clave
- `algorithm_version: string` — p. ej. `time_gap_v1` (auditoría / trazabilidad del algoritmo persistido en `capture_session_groups`)
- `assignment_status: string` — `unassigned` \| `assigned_existing` \| `assigned_new` (G4)
- `assigned_aisle_id: string | null` — pasillo vinculado al grupo cuando aplica (G4)
- `assigned_at: string(datetime) | null` — momento de la asignación (G4)

### CaptureSessionGroupsListResponse (G3)

- `groups: CaptureSessionGroupSummaryResponse[]`

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

## Temporal grouping (G3)

Agrupación **inventory-level** por segmentación temporal (gap configurable, default 60s vía `v3_capture_grouping_max_gap_seconds`). No crea `SourceAsset` ni materializa. La **asignación a pasillo por grupo** es G4 (ver más abajo).

### Endpoints

- **POST** `/{inventory_id}/capture-sessions/{session_id}/compute-groups`
  - **Respuesta 200:** `CaptureSessionGroupsListResponse` (`groups[]` con `algorithm_version` en cada fila).
  - **Precondiciones:** sesión **cerrada** (`closed_at != null`); estado no terminal prohibido para grouping (`cancelled`, `failed`, `confirmed` → error).
  - **Elegibilidad de ítems:** solo `import_status: imported` con `effective_capture_time != null` entran en clusters; el resto permanece con `group_id: null` en detalle de sesión.
  - **Idempotencia / recomputo:** volver a llamar **borra** grupos previos de esa sesión, limpia `group_id` en ítems y recalcula (mismos índices de grupo 1..N según datos; nuevos `group_id` UUID). **Se pierden** `assigned_aisle_id` / `assignment_status` / `assigned_at` (G4) porque las filas de grupo se eliminan.

- **GET** `/{inventory_id}/capture-sessions/{session_id}/groups`
  - **Respuesta 200:** misma forma que arriba (lista actualmente persistida).
  - Sesión debe existir para el inventario (mismo `404` que detalle si no aplica).

### Errores (códigos estables)

| HTTP | `code` | Cuándo |
|------|--------|--------|
| 404 | `CAPTURE_SESSION_NOT_FOUND` | `session_id` no pertenece al `inventory_id`. |
| 409 | `CAPTURE_SESSION_GROUPING_NOT_ALLOWED` | Sesión no cerrada, o estado `cancelled` / `failed` / `confirmed`. |
| 422 | `CAPTURE_SESSION_NO_ITEMS_FOR_GROUPING` | **Mismo código**, `detail` distinto (Option A): (a) sesión **sin ítems**; (b) hay ítems pero **ninguno califica** (no importados o sin `effective_capture_time`). El cliente debe usar `detail` para distinguir. |

### Política de producto / UI

- Puede haber ítems **sin grupo** después de un compute (no elegibles); deben seguir visibles en el detalle de sesión.
- La UI de grouping + asignación vive en la vista de detalle de sesión de importación.

## Group → aisle assignment (G4)

Puente operativo: cada grupo temporal puede vincularse a un **pasillo existente** o disparar la **creación de un pasillo nuevo** (mismo contrato de `code` que `POST /aisles`). No materializa (G5) ni preview de posiciones (G6).

### Endpoints

- **POST** `/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/assign-existing`
  - **Body JSON:** `{ "aisle_id": "<uuid>" }`
  - **Respuesta 200:** `CaptureSessionGroupsListResponse` (lista completa actualizada de grupos de la sesión).
  - **Precondiciones:** sesión cerrada y no terminal (misma política que grouping para `cancelled`/`failed`/`confirmed`); debe existir **al menos un** grupo persistido para la sesión (haber ejecutado `compute-groups` antes).
  - **Efecto:** `assignment_status = assigned_existing`, `assigned_aisle_id` y `assigned_at` seteados.

- **POST** `/{inventory_id}/capture-sessions/{session_id}/groups/{group_id}/create-aisle`
  - **Body JSON:** `{ "code": "<string 1..64>" }` — alineado con `CreateAisleRequest` (`code`, no nombre libre).
  - **Respuesta 200:** `CaptureSessionGroupsListResponse`.
  - **Efecto:** crea pasillo en el inventario, luego `assignment_status = assigned_new` y vínculo al nuevo `aisle_id`.

### Estados `assignment_status`

| Valor | Significado |
|-------|-------------|
| `unassigned` | Grupo calculado; aún sin pasillo operativo. |
| `assigned_existing` | Vinculado a un pasillo que ya existía en el inventario. |
| `assigned_new` | Pasillo creado en esta operación y vinculado al grupo. |

### Errores (G4)

| HTTP | `code` | Cuándo |
|------|--------|--------|
| 404 | `CAPTURE_SESSION_GROUP_NOT_FOUND` | `group_id` no existe en esa sesión. |
| 404 | `AISLE_NOT_FOUND_FOR_ASSIGNMENT` | `aisle_id` inexistente o inventario distinto al de la sesión. |
| 409 | `CAPTURE_SESSION_GROUP_ALREADY_ASSIGNED` | El grupo ya tiene asignación (`assigned_existing` / `assigned_new`). |
| 409 | `CAPTURE_SESSION_GROUP_ASSIGNMENT_NOT_ALLOWED` | Sesión abierta, sin grupos persistidos, o estado terminal incompatible. |
| 404 | `CAPTURE_SESSION_NOT_FOUND` | Sesión no pertenece al inventario. |
| 409 | `DUPLICATE_AISLE_CODE` (legacy / según mapper) | `create-aisle` con `code` duplicado en el inventario — mismo comportamiento que creación normal de pasillo. |

### Follow-up (G5)

- Materialización consumirá la relación **grupo → pasillo** preparada aquí; el contrato exacto de G5 queda fuera de este documento hasta implementarse.

## Nota de invariantes

- Upload a `items` **no** crea `SourceAsset`.
- Solo `materialize` crea `SourceAsset`.
- `process_aisle` opera exclusivamente sobre `SourceAsset`.
