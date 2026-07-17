# Fase 3 — Implementación (hardening)

## Estado al cierre

**Lista solo para rollout limitado / parcialmente validada.**  
No declarar producción general sin evidencia física, firma release y crash reporting operativo.

## Entregado en código

1. Auditoría, runbook, checklist, rollout/rollback, OEM, signing, crash reporting (docs).
2. Feature flags + versionado (`versionCode`, git SHA, build metadata).
3. Timeouts API diferenciados; HTTPS obligatorio en `production`.
4. Catálogo de errores tipado + ejes de lifecycle de foto (`photoLifecycle`).
5. Logger con buffer rotativo + export diagnóstico (Share).
6. Health checks locales (pantalla Diagnóstico).
7. Photo grids con `FlatList` virtualizada.
8. Limpieza de temporales / chequeo de espacio antes de captura.
9. Bridge WorkManager mínimo (unique work wake + JS drain; ownership SQLite).
10. CI `.github/workflows/mobile-validate.yml` + release manual `mobile-release.yml`.
11. Tests adicionales (flags, errores, timeouts, lifecycle, HTTPS prod).
12. Política uploads por datos móviles (`allowMobileDataUploads` + NetInfo cellular).

## No entregado / pendiente operativo

- Matriz física completa y DEVICE_EVIDENCE / DEVICE_MATRIX firmados.
- AAB/APK firmados con secretos CI (`ANDROID_KEYSTORE_*`).
- Sentry/Crashlytics con DSN (documentado; no forzar sin secret).
- WorkManager con upload HTTP nativo (solo wake/schedule + JS drain).
- ProGuard validado en release real.
- E2E Maestro/Detox automatizado.
- Lock multi-dispositivo (flag off; no requerido sin necesidad operativa).

## Veredicto

**Parcialmente validada — lista solo para rollout limitado** (equipo técnico / piloto interno) tras build debug y evidencia mínima en campo.  
**No** lista para producción general.
