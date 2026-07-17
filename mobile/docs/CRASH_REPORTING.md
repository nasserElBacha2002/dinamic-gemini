# Crash reporting (Fase 3)

## Decisión

No se fuerza Sentry/Crashlytics en el APK hasta que el proyecto provea:

1. DSN / proyecto aprobado
2. Política de redacción
3. Consentimiento / privacidad si aplica
4. Source maps en CI release

## Integración prevista

Cuando exista DSN:

- Inicializar solo en `staging` / `production`
- Tags: `environment`, `versionName`, `versionCode`, `gitSha`
- **Nunca** adjuntar: tokens, fotos, API keys, URLs firmadas, payloads multipart
- Sampling configurable vía env `DINAMIC_CRASH_SAMPLE_RATE`

Hasta entonces: logs locales + **Exportar diagnóstico** son el canal de soporte.
