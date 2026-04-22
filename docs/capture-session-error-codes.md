# Capture Session Error Codes (v3)

Catálogo de errores estructurados para frontend del módulo de ingesta.

Referencia primaria de endpoint/estado para interpretar estos errores:
`docs/capture-session-api-contract.md`.

Formato esperado:

```json
{
  "code": "ERROR_CODE",
  "detail": "human readable"
}
```

## Errores de scope / existencia

- `CAPTURE_SESSION_NOT_FOUND`
  - **HTTP:** 404
  - **Cuando ocurre:** `session_id` no existe o no pertenece al `inventory_id`/`aisle_id` solicitado.

- `OPEN_CAPTURE_SESSION_EXISTS`
  - **HTTP:** 409
  - **Cuando ocurre:** intento de crear sesión excede política de sesiones abiertas por pasillo.

## Errores de estado de sesión

- `CAPTURE_SESSION_INVALID_STATE`
  - **HTTP:** 409
  - **Cuando ocurre:** transición no permitida por estado actual (close/cancel/offset u otras).

- `CAPTURE_SESSION_NOT_ACCEPTING_UPLOADS`
  - **HTTP:** 409
  - **Cuando ocurre:** upload en sesión cerrada o terminal (`CANCELLED/FAILED/CONFIRMED`).

- `CAPTURE_SESSION_PREVIEW_NOT_ALLOWED`
  - **HTTP:** 409
  - **Cuando ocurre:** preview fuera de estado permitido o sin cierre de sesión.

## Errores de upload staging

- `EMPTY_UPLOAD`
  - **HTTP:** 422
  - **Cuando ocurre:** request sin archivos.

- `ZERO_BYTE_FILE`
  - **HTTP:** 422
  - **Cuando ocurre:** archivo vacío o tamaño cero.

- `UNSUPPORTED_ASSET_TYPE`
  - **HTTP:** 400
  - **Cuando ocurre:** MIME/tipo de archivo no soportado.

- `CAPTURE_SESSION_DUPLICATE_ITEM_CONTENT`
  - **HTTP:** 409
  - **Cuando ocurre:** hash duplicado dentro de la misma sesión.

- `CAPTURE_SESSION_UPLOAD_BATCH_TOO_LARGE`
  - **HTTP:** 422
  - **Cuando ocurre:** cantidad de archivos supera el máximo permitido por request.

- `CAPTURE_SESSION_STAGING_FILE_TOO_LARGE`
  - **HTTP:** 422
  - **Cuando ocurre:** archivo supera límite configurado de tamaño.

## Errores de filtros / validación

- `CAPTURE_SESSION_STATUS_FILTER_INVALID`
  - **HTTP:** 422
  - **Cuando ocurre:** query `status` inválida en listado de sesiones.

- `CAPTURE_SESSION_INVALID_CLOCK_OFFSET`
  - **HTTP:** 422
  - **Cuando ocurre:** `clock_offset_seconds` fuera de rango configurado.

- `CAPTURE_SESSION_INVALID_IDEMPOTENCY_KEY`
  - **HTTP:** 422
  - **Cuando ocurre:** key vacía o inválida para materialización.

## Errores de materialización

- `CAPTURE_SESSION_MATERIALIZATION_NOT_ALLOWED`
  - **HTTP:** 409
  - **Cuando ocurre:** estado de sesión o set de ítems no apto para materializar.

- `CAPTURE_SESSION_ALREADY_MATERIALIZED`
  - **HTTP:** 409
  - **Cuando ocurre:** sesión ya materializada o intento con key distinta tras materialización previa.

- `CAPTURE_SESSION_MATERIALIZATION_FAILED`
  - **HTTP:** 500
  - **Cuando ocurre:** fallo inesperado en lectura staging/escritura storage/persistencia durante materialización.

## Nota de consistencia

- Los flujos de `capture-sessions` deben usar errores estructurados para que frontend pueda branch por `code`.
- Excepción estándar framework: validaciones de FastAPI/Pydantic pueden responder con `{"detail": [...]}`.
