# Plan de implementación incremental — Móvil

Principio: **servidor intacto por defecto**; cada fase feature-flagged y reversible.

---

## Fase 0 — Baseline observabilidad (1–3 días)

**Objetivo:** Medir el cuello de botella real en campo (S10+).

**Alcance:**
- Métricas: prepare_ms, original_bytes, prepared_bytes, upload_ms, batch_size, retry_count, network_type, time_to_process_start, time_to_job_terminal.
- Logging estructurado sin PII de etiqueta.

**Módulos:** `uploadQueue.ts`, `photoPrepare.ts`, `processingService.ts`, `logging.ts`

**Fuera de alcance:** Cambios de backend pipeline.

**Pruebas:** unit de emisión de métricas; checklist manual 20/50 fotos Wi-Fi y 4G.

**Rollback:** flag off / quitar reporters.

**DoD:** Dashboard o export con p50/p95 de upload vs process duration.

---

## Fase 1 — Optimización de prepare/upload (3–7 días)

**Objetivo:** Reducir bytes y mejorar throughput sin cambiar process.

**Alcance:**
- Aplicar `DEFAULT_MAX_DIMENSION_PX` (o config desde `/upload-limits`).
- Calidad JPEG adaptativa (Wi-Fi vs cellular).
- Wire `AbortSignal` en cancel.
- Ajustar concurrencia 2–4 según NetInfo (capada).
- Wire o eliminar flag `heicConvertToJpeg`.

**Módulos:** `photoPrepare.ts`, `uploadQueue.ts`, `uploadLimitsService.ts`, `config` backend advisory fields (aditivo).

**Fuera de alcance:** Signed URL, WorkManager real, CODE_SCAN local.

**Pruebas:** `fase2UploadCore`, prepare tests, packing 413.

**Métricas:** ratio bytes ↓ ≥30% en fotos típicas (validar con baseline F0).

**Rollback:** flag `mobile_upload_dimension_cap=0`.

**DoD:** Misma API assets; tests verdes; mejora medida en dispositivo.

---

## Fase 2 — Background upload durable (1–2 semanas)

**Objetivo:** Drenar cola con app en background / tras kill (best-effort Android).

**Alcance:**
- Implementar WorkManager o FGS de upload (reemplazar noop).
- Notificación de progreso.
- Reconciliación SQLite al reopen (ya existe; endurecer).

**Módulos:** `modules/capture-foreground-service`, `backgroundWork.ts`, `uploadQueue.ts`

**Dependencias:** Fase 1 (prepare estable).

**Fuera de alcance:** OCR local; cambios process_aisle.

**Pruebas:** kill app mid-upload; Doze; reboot; battery saver Samsung.

**Rollback:** volver a noop scheduler.

**DoD:** Tras kill+reopen, cola continúa; documentar límites OEM honestos.

---

## Fase 3 — Signed upload aditivo (opcional, 1–2 semanas)

**Objetivo:** Evitar proxy de bytes por API.

**Alcance:**
- `upload-intent` → URL firmada PUT.
- Confirmación `upload-complete` con hash.
- Mantener multipart legacy.

**Módulos:** backend assets routes (nuevas), storage adapters, mobile `aisleAssetsApi.ts`

**Fuera de alcance:** Cambiar pipeline CV.

**Pruebas:** contract + e2e 1 y N archivos; URL expirada; size mismatch.

**Rollback:** flag `mobile_signed_upload=0` → multipart.

**DoD:** Paridad de `SourceAsset` creado; authz intacta.

---

## Fase 4 — Contract pack CODE_SCAN (3–5 días)

**Objetivo:** Parser QR/barcode compartido por contratos.

**Alcance:**
- Golden fixtures Python ↔ TypeScript port de grammar.
- Documentar `pipeline_version`.

**Módulos:** `code_scan_qr_payload.py`, nuevo `mobile/src/core/labelPayload.ts`, tests ambos lados.

**Fuera de alcance:** SDK nativo aún.

**DoD:** Contract tests CI fallan si diverge.

---

## Fase 5 — CODE_SCAN local canario (2–3 semanas)

**Objetivo:** Resolver etiquetas encodeadas on-device.

**Alcance:**
- Integrar SDK barcode (ML Kit u otro).
- `LocalCodeScanStrategy` detrás de flag.
- Persist draft en SQLite (`detected_code`, `detected_quantity`, `fallback_required`).
- UI progreso (sin review/edit).

**Dependencias:** Fases 0–2, 4.

**Fuera de alcance:** OCR; preliminary sync API (puede stub local-only primero).

**Pruebas:** unit strategy; device tests códigos PIPE/DI1/PLAIN; memoria 50–100 imgs.

**Rollback:** flag off.

**DoD:** Resolve rate medido; fallos marcan fallback; uploads siguen ocurriendo.

---

## Fase 6 — Sync preliminary + process unresolved (2–3 semanas)

**Objetivo:** Híbrido real con servidor autoridad.

**Alcance:**
- Endpoint aditivo preliminary results.
- Validación server + idempotencia.
- Mobile sync + `POST /process` solo para unresolved / rejected.
- Observabilidad accept/reject.

**Fuera de alcance:** Edición móvil; GLOBAL_BATCH changes; OCR local.

**Pruebas:** contract, concurrency, stale version, duplicate client_result_id, offline→online.

**Rollback:** flag sync off → ignore drafts, full process.

**DoD:** Web review ve posiciones aceptadas; pipeline remoto intacto para el resto.

---

## Fase 7 — Hardening y rollout (continuo)

- Rate limits, wipe logout, retention cleanup.
- Remote config de flags por cliente/dispositivo.
- Decisión go/no-go OCR local basada en métricas (default: no).

---

## Orden resumido

```text
F0 metrics → F1 prepare/upload → F2 background → [F3 signed optional]
  → F4 QR contracts → F5 local CODE_SCAN → F6 sync hybrid → F7 hardening
```

## Explicitamente fuera del programa (hasta nueva auditoría)

- OCR local producción
- Pipeline LLM en dispositivo
- Runtime Python embebido
- Reemplazo del process_aisle actual
- UI móvil de corrección/aprobación
