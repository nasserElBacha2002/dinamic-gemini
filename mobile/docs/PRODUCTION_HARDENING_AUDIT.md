# Production hardening — auditoría inicial (pre-hardening)

Fecha: 2026-07-17  
Ámbito: `mobile/` únicamente. Sin cambios de backend.

## Veredicto

**No listo para producción general.** Núcleo captura ordenada + carga en background **parcialmente productivo** (código + tests unitarios). Bloqueantes: evidencia física E2E, CI mobile, firma release, crash reporting, WorkManager nativo completo, UI no virtualizada (pre-hardening).

## Clasificación

| Componente | Estado |
|------------|--------|
| Arquitectura (capas core/features/services) | Parcial |
| Dependencias Expo 51 / RN 0.74.5 | Parcial |
| Módulo FGS nativo | Parcial |
| WorkManager | Prototipo → se introduce bridge mínimo en hardening |
| SQLite + migraciones v1–v4 | Parcial |
| SecureStore tokens | Parcial |
| ApiClient JSON/multipart/refresh | Parcial |
| UploadQueue | Parcial |
| Reconciliación GET assets | Parcial |
| JobMonitor (timers JS) | Parcial |
| Logging estructurado | Parcial (console → rotativo en hardening) |
| Env / app.config | Parcial |
| Build Android (android/ gitignored) | No validado en repo |
| Permisos fotos-only | Parcial |
| Contratos backend documentados | Productivo (docs) |
| Tests unitarios/integración | Parcial |
| Evidencia física DEVICE_EVIDENCE | No validado |
| Seguridad (API key en APK) | Riesgo crítico (mitigar: key pública / sin privilegios) |
| Performance UI (ScrollView) | Prototipo → FlatList en hardening |
| CI mobile | Riesgo crítico → workflow en hardening |
| Crash reporting | No validado (opcional documentado; sin DSN) |
| Feature flags | No validado → tipados por build en hardening |
| Export diagnóstico | No validado → implementado en hardening |
| Network security / cleartext | Parcial → harden prod en hardening |
| ProGuard/R8 | No validado (requiere release firmado) |
| Versionado versionCode/SHA | Prototipo → extendido en hardening |

## Dispositivos y SDK objetivo (definidos)

| Parámetro | Valor |
|-----------|--------|
| minSdkVersion | 24 (Android 7.0) |
| targetSdkVersion | 34 (Android 14) |
| compileSdkVersion | 34 |
| ABI | arm64-v8a, armeabi-v7a |
| Validar | Android 12–14; Android 15 cuando toolchain lo permita |
| Fabricantes piloto | Samsung, Motorola, Pixel; Xiaomi con doc OEM |

## Riesgos críticos abiertos (post-auditoría)

1. Sin matriz física firmada.
2. Sin keystore/release pipeline en CI.
3. Uploads/polling mueren si el proceso JS es matado (WorkManager completo = follow-up).
4. `DINAMIC_API_KEY` empaquetada = pública.

## Qué implementa el hardening en código

Ver `PRODUCTION_HARDENING_IMPLEMENTATION.md`.
