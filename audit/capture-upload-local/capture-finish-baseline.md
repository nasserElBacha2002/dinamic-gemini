# Capture finish baseline (Fase 0)

## Cómo generar

1. Ejecutar captura en dispositivo con `captureFinishInstrumentation=true`.
2. Exportar filas `observability_events` (nombres `capture.finish_*`, `photo.prepare_*`, `photo.upload_*`).
3. Pasar por `buildBaselineReport(rowsToParsedEvents(rows))`.

## Métricas nuevas en el reporte

- `metrics.finish_ms` — duración total (`capture.finish_completed`)
- `metrics.finish_media_store_check_ms`
- `metrics.finish_validation_wait_ms`
- `finishExtra.new_media_candidates_events`
- `finishExtra.skipped_full_rescan_events`
- `finishExtra.orphan_reclaimed` / `upload_healed`

## Baseline de dispositivo

**Pendiente:** correr en S10+/campo y adjuntar p50/p90/p95 reales. La instrumentación está lista; sin runs de campo este archivo no puede afirmar el budget &lt;1s.
