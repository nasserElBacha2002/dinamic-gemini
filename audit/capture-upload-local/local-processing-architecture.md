# Local processing architecture (Fase 3)

## Semántica

- Estado de sesión `local_completed`: cierre de pasillo **sin** exigir upload ni `/process`.
- Transiciones: `review → local_completed → uploading` (subida posterior opcional).
- Freeze watermark (Fase 1) define el set congelado usado por CSV y upload.

## UX

En `ReviewScreen` (flags `localCompletion` / `mobileCsvExport`):

1. **Subir imágenes ahora** → `completeReview` + cola
2. **Guardar y subir más tarde** → `completeLocalSession` + enqueue background + Actividad local
3. **Exportar resultados CSV** → export offline + share sheet

Copy explícito: resultados locales ≠ OCR/fallback remoto.

## Actividad local

`LocalActivityScreen` lista sesiones abiertas vía `capture.listActivitySessions()` + progreso de upload.
