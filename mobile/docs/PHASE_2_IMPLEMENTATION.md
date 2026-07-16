# Fase 2 — Implementación (carga progresiva + procesamiento)

## Alcance entregado

- Migraciones SQLite v3/v4: campos de upload/procesamiento, `upload_batches`, `processing_jobs`, unicidad `(capture_session_id, client_file_id)`.
- Estados locales de upload separados del lifecycle de captura/estabilidad.
- Exclusividad de captura solo en `preparing|active|paused|finishing|review` (permite segundo pasillo mientras otro sube/procesa).
- `UploadLimitsService` → `GET /api/v3/config/upload-limits` con fallback conservador.
- `UploadQueue` persistente: micro-lotes, concurrencia ≤2, backoff, pausa offline/auth, respuestas parciales, DELETE remoto.
- `ProcessingService` + `JobMonitor` contra `POST .../process`, `GET .../status`.
- UI: pantallas de cargas, procesamiento y actividad.
- HEIC/HEIF → JPEG en dispositivo antes del upload (documentado).
- Contratos backend: `docs/PHASE_2_BACKEND_CONTRACTS.md`.

## Limitaciones / pendiente de evidencia

- WorkManager nativo completo: recuperación al arrancar JS + cola persistente; no hay worker Android independiente aún.
- E2E físico / staging (20+20 fotos, offline, 401, respuesta perdida) pendiente de evidencia en dispositivo.
- Reconciliación GET assets no expone `client_file_id` en listado; se usa idempotencia del POST + `backend_asset_id` local.

## Validación local

```bash
cd mobile
npm run typecheck
npm run lint
npm test
```

Estado: **parcialmente validada** — lista para piloto controlado tras E2E en dispositivo contra staging.
