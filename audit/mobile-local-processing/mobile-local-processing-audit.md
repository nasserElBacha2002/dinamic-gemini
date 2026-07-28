# Auditoría — Procesamiento local de imágenes en aplicación móvil

**Fecha:** 2026-07-23  
**Alcance:** `mobile/`, APIs v3 de assets/process, pipeline CODE_SCAN / INTERNAL_OCR / EXTERNAL_FALLBACK  
**Modo:** solo lectura (sin cambios de código productivo)

---

## 1. Resumen ejecutivo

La app móvil actual es un **cliente de captura Android (Expo 51 / RN 0.74)** que:

1. detecta fotos nuevas en la galería;
2. las encola en SQLite;
3. las prepara (HEIC→JPEG / resize si supera límite de tamaño);
4. las sube por **multipart autenticado** al API v3;
5. dispara **un** `POST .../process` con modo `CODE_SCAN` o `INTERNAL_OCR`;
6. espera el pipeline **completo en el servidor**.

**No hay OCR ni barcode local.** WorkManager es un no-op; la recuperación post-muerte del proceso es “reabrir la app + restaurar SQLite”.

El cuello de botella percibido coincide con la evidencia de arquitectura: **transferencia de bytes a través del backend** (no hay URL firmada de subida), con concurrencia baja (1–2 lotes), timeout multipart 120s, y preparación local solo reactiva (no hay tope proactivo de dimensión). El tiempo de OCR/LLM remoto es un segundo factor, no el primero en la ruta de “esperando que las fotos lleguen”.

**Recomendación de estado:** ver `mobile-processing-audit-status.txt` → `RECOMMENDED_WITH_CONDITIONS`.

Estrategia elegida (detalle en `mobile-processing-recommended-strategy.md`):

1. **Fase inmediata:** optimizar carga (compresión/dimensión, background upload real, métricas).
2. **Fase siguiente:** CODE_SCAN local opcional + sync de resultados livianos + upload diferido de evidencia.
3. **No** replicar OCR/pipeline completo ni embeber Python en el dispositivo.

---

## 2. Arquitectura actual

### 2.1 Stack móvil (evidencia)

| Capa | Tecnología | Evidencia |
|------|------------|-----------|
| Runtime | Expo ~51, RN 0.74.5, Android-only | `mobile/package.json`, `app.config.ts` |
| Navegación | State machine en `App.tsx` (sin React Navigation) | `mobile/App.tsx` |
| Persistencia | `expo-sqlite` → `dinamic_mobile.db` | `mobile/src/database/database.ts` |
| Galería | `expo-media-library` (sin cámara in-app) | `mobile/src/native/mediaStore.ts` |
| Transform | `expo-image-manipulator` | `mobile/src/features/upload/photoPrepare.ts` |
| Auth tokens | `expo-secure-store` | `mobile/src/services/secureStorage/tokenStorage.ts` |
| Red | fetch + NetInfo | `apiClient.ts`, `connectivity.ts` |
| FGS | módulo nativo `capture-foreground-service` | captura activa, no upload HTTP |
| WorkManager | API JS/Kotlin **noop** | `mobile/src/native/backgroundWork.ts` |

### 2.2 Stack backend (evidencia)

| Capa | Tecnología |
|------|------------|
| API | FastAPI v3 bajo `Depends(get_current_admin)` |
| Upload | Multipart → `UploadAisleAssetsUseCase` → object storage vía API |
| Jobs | `process_aisle` en `inventory_jobs` |
| Estrategias | CODE_SCAN, INTERNAL_OCR, LEGACY_LLM (rechazado en jobs nuevos), EXTERNAL_FALLBACK |
| Persistencia | SQL Server + artifact storage local/S3/GCS |

### 2.3 Flujo completo

```text
Login → Inventarios → Pasillos → CaptureScreen (galería + FGS)
  → ReviewScreen → UploadQueue.enqueueSession
  → preparePhotoForUpload → POST .../assets (multipart, batches)
  → ProcessingService.startProcess → POST .../process (1×, idempotent)
  → JobMonitor poll → ResultsScreen (resumen read-only)
```

Servidor (después de process):

```text
Worker → CODE_SCAN | INTERNAL_OCR (por asset)
  → EXTERNAL_FALLBACK (GLOBAL_BATCH o PER_ASSET) si elegible
  → Persist posiciones / evidencia
  → Review en web (fuera de la app móvil)
```

---

## 3. Flujo de carga — detalle operativo

### 3.1 Requests

| Operación | Cantidad |
|-----------|----------|
| Upload por imagen | 1 slot en multipart; N fotos ⇒ `ceil(N / max_files)` POSTs |
| max_files / request | Server default 10 (`MAX_FILES_PER_UPLOAD_REQUEST`); mobile fallback histórico 5 |
| Concurrencia de batches | Advisory `UPLOAD_BATCH_CONCURRENCY` (default 2); mobile `Math.min(2, …)` |
| Process | **1** `POST .../process` por pasillo (key `mobile-process:{sessionId}:{runId}`) |
| Polling | `JobMonitor` in-process |

### 3.2 Preparación local

- HEIC/HEIF → JPEG `compress: 0.92` (`photoPrepare.ts`)
- Si `size > maxFileSizeBytes` → resize width + JPEG `0.85`
- Constante `DEFAULT_MAX_DIMENSION_PX = 3000` **definida pero no aplicada** en `preparePhotoForUpload` (`photoPrepare.ts` vs `shared/constants/photoPrepare.ts`)
- Sin strip EXIF explícito; re-encode puede perder EXIF como efecto secundario
- `ACCESS_MEDIA_LOCATION` deshabilitado en `app.config.ts`

### 3.3 Persistencia local (ya existe cola)

Tablas: `capture_sessions`, `capture_photos`, `upload_batches`, `processing_jobs` (`captureSchema.ts`).

Estados de upload en foto: queued / preparing / uploading / uploaded / retryable_error / permanent_error / excluded.

Recuperación: `UploadQueue.restoreAndStart()`, `CaptureService.restoreLatestOpen()` (active→paused), `JobMonitor.restorePendingJobs()`.

### 3.4 Background

| Capacidad | Estado real |
|-----------|-------------|
| FGS captura | Implementado |
| Upload con app cerrada | **No** (WorkManager noop) |
| OCR/CODE_SCAN local | **No** |
| Foreground upload mientras app abierta | Sí (cola + ticks) |

---

## 4. Cuello de botella — hallazgos con evidencia

### [HIGH] Transferencia de bytes vía backend (sin signed PUT)

**Evidencia:**
- `mobile/src/features/upload/aisleAssetsApi.ts` → `POST .../assets`
- `backend/src/api/routes/v3/assets.py` → spool + `put_object` en servidor
- Presign solo para **GET** de display (`image-display-url`)

**Impacto:** Doble hop (device→API→storage), saturación del API, timeouts 120s, percepción de “lentitud de carga”.

**Recomendación:** Fase A — signed upload o al menos compresión/dimensión más agresiva antes de signed URL.

### [HIGH] WorkManager es no-op — uploads no sobreviven process death

**Evidencia:**
- `mobile/src/native/backgroundWork.ts` (comentario y `mode: 'noop_js_restore_on_open'`)
- Módulo Kotlin documentado como stub

**Impacto:** Usuario cierra app → cola queda en SQLite hasta reopen; mala UX en lotes grandes.

### [MEDIUM] Sin tope proactivo de resolución

**Evidencia:** `DEFAULT_MAX_DIMENSION_PX` no usado en `preparePhotoForUpload`; solo resize si supera `maxFileSizeBytes` (típicamente 25–500 MB según config).

**Impacto:** Fotos 12MP+ se suben casi sin reducir si caben en el límite de tamaño → más bytes, más tiempo de red.

### [MEDIUM] Concurrencia de upload limitada a 1–2

**Evidencia:** `UploadQueue.tick` + `UPLOAD_BATCH_CONCURRENCY`.

**Impacto:** En Wi-Fi sano puede quedar throughput bajo; en 4G protege el dispositivo. Falta perfil adaptativo.

### [MEDIUM] SHA-256 de upload aisle se calcula y se descarta

**Evidencia:** spool multipart computa digest; aisle materializer no persiste content-hash; dedup solo por `(aisle_id, upload_batch_id, client_file_id)`.

**Impacto:** No hay deduplicación por contenido en path móvil principal; re-subidas duplican storage.

### [INFO] Procesamiento remoto no es el primer síntoma de UX

**Evidencia:** Mobile espera uploads completos antes / en paralelo a process según flujo de pantallas; process es 1 request; CODE_SCAN/OCR/LLM ocurren *después* de que los assets existen.

**Impacto:** Optimizar solo el LLM no elimina la demora de “subiendo fotos”.

### [INFO] ResultsScreen es read-only (cumple restricción de no review)

**Evidencia:** `ResultsScreen.tsx` — resumen de estado, sin edición/aprobación.

---

## 5. Componentes relevantes

| Área | Módulos |
|------|---------|
| Captura | `captureService.ts`, `mediaStore.ts`, `incrementalScan.ts`, `scanCoordinator.ts` |
| Upload | `uploadQueue.ts`, `photoPrepare.ts`, `uploadBatching.ts`, `aisleAssetsApi.ts` |
| Process | `processingService.ts`, `processingMode.ts`, `jobMonitor.ts` |
| Backend upload | `assets.py`, `upload_aisle_assets.py`, `multipart_aisle_uploads.py` |
| Backend process | `StartAisleProcessingUseCase`, `AisleProcessingOrchestrator`, strategies, fallback |
| Dominio puro reutilizable | `encoded_label_payload_parser.py`, `code_scan_qr_payload.py`, modes/resolver, fallback eligibility |

---

## 6. Reutilización (síntesis)

Ver tabla completa en `mobile-processing-reuse-map.md`.

- **Reutilizable vía contrato / port:** enums de modo, grammar de QR, packing limits, idempotency shapes.
- **No reutilizable en móvil:** Tesseract/OCR interno, hybrid pipeline, LLM, SQL Server repos, storage adapters.
- **Ya duplicado en móvil:** límites de upload, prepare HEIC, process body builder.

---

## 7. Acoplamientos

- Auth móvil = mismo `get_current_admin` JWT (no hay upload-scoped token).
- Upload acoplado al API process (bytes atraviesan FastAPI).
- Feature flags móviles (`DINAMIC_FLAG_*`) vs env backend (`CODE_SCAN_*`) — no unificados.
- `heicConvertToJpeg` flag existe pero prepare siempre convierte HEIC.

---

## 8. Seguridad (síntesis)

Ver `mobile-processing-security-review.md`.

Trust boundary clara: **el dispositivo no es confiable**; resultados locales futuros deben validarse en servidor. Tokens en SecureStore. No hay secretos de LLM/OCR en la app hoy.

---

## 9. Compatibilidad Android / Samsung S10+

- Target razonable (Android 9+, Expo 51).
- OEM Samsung: Doze + battery optimization afectan WorkManager/FGS — cualquier worker real debe usar FGS para uploads largos o aceptar deferral.
- Sin hardcode al S10+; falta `DeviceCapabilityProfile` (aún no existe).

---

## 10. Métricas actuales — huecos

No hay instrumentación de:

- bytes originales vs preparados;
- tiempo prepare / upload / TTFB process;
- network type;
- retries por causa.

Impide cuantificar mejora de Alternativa A sin instrumentar primero.

---

## 11. Conclusión

El sistema ya tiene **cola persistente y preparación básica**. El mayor ROI inmediato es **reducir bytes y completar uploads en background**, no portar el OCR del servidor. CODE_SCAN local es el único procesamiento on-device con alto valor / bajo riesgo de divergencia, si se limita a payloads encodeados y el servidor sigue siendo autoridad.
