# Estrategia recomendada — Aceleración móvil compatible

**Estado:** `RECOMMENDED_WITH_CONDITIONS`  
**Nombre corto:** **Upload-first + optional local CODE_SCAN hybrid**

---

## 1. Decisión

Implementar de forma incremental:

1. **Optimización de carga y background upload** (Alternativa A) — obligatorio.
2. **CODE_SCAN local opcional** con sync de resultados y fallback al `POST .../process` existente (Alternativa B dentro de E).
3. **No** OCR local completo, **no** pipeline local completo, **no** runtime Python embebido.

El **servidor permanece fuente de verdad consolidada**. El móvil nunca edita/aprueba resultados (ya cumplido por `ResultsScreen`).

---

## 2. Arquitectura objetivo

```text
Mobile
├── Presentation (job list, capture, upload progress, summary)
├── Application
│   ├── CaptureSession / EnqueueImages
│   ├── PrepareImages (dimension + compress policy)
│   ├── LocalCodeScanStrategy (optional, feature-flagged)
│   ├── UploadEvidence (queue + FGS/WorkManager)
│   ├── SyncPreliminaryResults (new additive API)
│   └── StartServerProcessForUnresolved (existing /process)
├── Domain (LocalJob, LocalImageTask, SyncState, Policies)
└── Infrastructure (SQLite existente, MediaStore, Barcode SDK, HTTP)

Server (unchanged core)
├── Existing multipart assets OR additive signed upload
├── Existing process_aisle pipeline (CODE_SCAN / OCR / GLOBAL_BATCH)
├── Additive: accept preliminary mobile results (validated)
└── Web review (authoritative corrections)
```

### Responsabilidades

| Quién | Qué |
|-------|-----|
| Móvil | Captura, prepare, cola, CODE_SCAN local (flag), upload evidencia, sync preliminar, disparar process para unresolved |
| Servidor | Validar/aceptar preliminares, ownership, pipeline completo, fallback LLM, persistencia final, review web |
| Antes de subir | Normalizar/comprimir; opcional scan barcode |
| Después de subir | Process servidor solo para pendientes; reconciliar |
| Sin conexión | Prepare + CODE_SCAN + cola; no claim de “resultado final” |
| Fallo local | Marcar `fallback_required` → flujo remoto existente |
| Fallo sync | Reintento idempotente; no duplicar posiciones |
| Servidor rechaza | Conservar evidencia; encolar process remoto; UI “requiere servidor” |

---

## 3. Contratos nuevos (aditivos)

Propuestos (no implementar en esta auditoría):

1. `POST /api/v3/.../mobile-preliminary-results` (o extensión de action idempotent)
   - Body: `client_result_id`, `asset_client_file_id` o `source_asset_id`, `internal_code`, `quantity?`, `method=LOCAL_CODE_SCAN`, `payload_raw`, `pipeline_version`, `device_id`, `idempotency_key`
2. Opcional: `POST .../assets/upload-intent` → signed PUT URLs
3. Extensión de `GET /config/upload-limits` con `max_edge_dimension`, `preferred_jpeg_quality`, `local_code_scan_enabled`

**No modificar** semántica de `POST .../assets` ni `POST .../process` existentes sin versión/compat.

---

## 4. Estados (máquina)

### LocalJob
`CREATED → IMAGES_QUEUED → LOCAL_PROCESSING → UPLOAD_PENDING → UPLOADING → SERVER_PROCESS_PENDING → COMPLETED`

Alternativos: `WAITING_FOR_NETWORK`, `RETRY_SCHEDULED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`, `CANCELLED`, `PARTIALLY_SYNCED`

### LocalImageTask
`CAPTURED → PREPARED → LOCAL_SCAN_* → RESULT_SYNC_* → UPLOAD_* → SERVER_REQUIRED | DONE`

Transiciones prohibidas: `DONE → LOCAL_SCAN`; sobrescribir resultado `ACCEPTED` del servidor con preliminar más viejo.

### Capas de resultado
1. `local_draft`
2. `sync_pending`
3. `server_accepted` (autoridad)
4. `server_reprocessed` (gana sobre local)
5. `final` (post-review web; móvil solo lectura)

---

## 5. Idempotencia y sync

- UUID `client_file_id` / `upload_batch_id` (ya existen).
- Nuevo `client_result_id` por intento de resultado local.
- Hash de archivo (persistir SHA-256 actualmente descartado en aisle upload).
- Servidor: upsert por `(job_or_aisle, client_result_id)` o `(source_asset_id, method, result_version)`.
- Regla: **servidor nunca pierde ante draft local más viejo**; `If-Match` / version token.

Fuente de verdad: **servidor**.

---

## 6. Política de carga de imágenes

| Caso | Política recomendada (Fase 2+) |
|------|--------------------------------|
| Resuelto local CODE_SCAN | Subir evidencia (JPEG preparado) en background; no bloquear UI |
| Unresolved | Subir lo antes posible → process servidor |
| Auditoría | Conservar evidencia; no borrar local hasta `server_accepted` + ACK |
| Wi-Fi only originales | Flag opcional; default subir preparado siempre |
| Thumbnails-only | **No** como única evidencia (rompe review web) |

---

## 7. Feature flags

| Flag | Propósito |
|------|-----------|
| `mobile_upload_dimension_cap` | Activar tope px |
| `mobile_upload_fgs_worker` | FGS/WorkManager real |
| `mobile_signed_upload` | Signed PUT |
| `mobile_local_code_scan` | CODE_SCAN on-device |
| `mobile_preliminary_result_sync` | POST resultados preliminares |
| `mobile_defer_upload_when_resolved` | (opcional, off by default) |

Rollout: métricas actuales → A → background → CODE_SCAN canario → sync → ampliar clientes.

---

## 8. Fallback

```text
if !flag(local_code_scan) or !device_capable:
    existing upload + POST /process
elif local_scan unresolved or failed:
    upload + POST /process (unchanged pipeline)
elif preliminary rejected by server:
    enqueue server process; keep evidence
elif offline:
    queue prepare/scan/upload; no final claim
```

---

## 9. Seguridad

- Resultados locales = untrusted input.
- Validar schema, ownership aisle/inventory, code grammar, quantity bounds, sizes, duplicates.
- No API keys de LLM/OCR/storage en APK.
- Signed URLs TTL corto + content-type/size enforcement.

---

## 10. Métricas de éxito

**Móvil:** p50/p95 tiempo prepare, bytes ratio, upload duration, queue drain after kill, local resolve rate, battery delta.

**Servidor:** preliminary accept/reject rate, remote process avoided %, time-to-first-accepted-result, conflict count.

**Producto:** tiempo hasta “hay resultado usable en web” y tiempo hasta “uploads 100%”.

---

## 11. Criterios de aceptación (estrategia)

- Pipeline servidor sin cambios de comportamiento por defecto.
- Con flags off = comportamiento idéntico al actual.
- Con flags on: CODE_SCAN local no bloquea upload de evidencia.
- Fallo local → process remoto.
- Móvil sin UI de review/edición.
- Contract tests parser QR Python ↔ TS.
- Medición baseline antes de declarar mejora %.

---

## 12. Componentes que NO deben tocarse (salvo flags aditivos)

- Hybrid LLM prompt contracts
- INTERNAL_OCR engine server
- PersistAisleResult delete-all semantics
- Web review workflows
- Auth model (salvo tokens scoped futuros opcionales)
