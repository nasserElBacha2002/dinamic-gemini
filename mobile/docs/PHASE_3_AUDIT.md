# Fase 3 — Auditoría inicial (pre-hardening)

Fecha: 2026-07-17  
Ámbito: `mobile/` únicamente. Sin cambios de backend.

## Veredicto

**No listo para producción general.** Núcleo Fase 1–2 **parcialmente productivo** (código + tests unitarios). Bloqueantes: evidencia física E2E, CI mobile, firma release, crash reporting, WorkManager nativo completo, UI no virtualizada (pre-Fase 3).

## Clasificación

| Componente | Estado |
|------------|--------|
| Arquitectura (capas core/features/services) | Parcial |
| Dependencias Expo 51 / RN 0.74.5 | Parcial |
| Módulo FGS nativo | Parcial |
| WorkManager | Prototipo → se introduce bridge mínimo en Fase 3 |
| SQLite + migraciones v1–v4 | Parcial |
| SecureStore tokens | Parcial |
| ApiClient JSON/multipart/refresh | Parcial |
| UploadQueue | Parcial |
| Reconciliación GET assets | Parcial |
| JobMonitor (timers JS) | Parcial |
| Logging estructurado | Parcial (console → rotativo en Fase 3) |
| Env / app.config | Parcial |
| Build Android (android/ gitignored) | No validado en repo |
| Permisos fotos-only | Parcial |
| Contratos backend documentados | Productivo (docs) |
| Tests unitarios/integración | Parcial |
| Evidencia física DEVICE_EVIDENCE | No validado |
| Seguridad (API key en APK) | Riesgo crítico (mitigar: key pública / sin privilegios) |
| Performance UI (ScrollView) | Prototipo → FlatList en Fase 3 |
| CI mobile | Riesgo crítico → workflow en Fase 3 |
| Crash reporting | No validado (opcional documentado; sin DSN) |
| Feature flags | No validado → tipados por build en Fase 3 |
| Export diagnóstico | No validado → implementado en Fase 3 |
| Network security / cleartext | Parcial → harden prod en Fase 3 |
| ProGuard/R8 | No validado (requiere release firmado) |
| Versionado versionCode/SHA | Prototipo → extendido en Fase 3 |

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

## Qué implementa Fase 3 en código

Ver `PHASE_3_IMPLEMENTATION.md`.
