# Firma Android (Fase 3)

## Reglas

- **No** versionar keystore productivo, passwords ni alias secrets.
- Debug: keystore de desarrollo local / Expo default.
- Release interno / Play: secret manager de CI + variables seguras.

## Artefactos esperados

| Artefacto | Comando | Uso |
|-----------|---------|-----|
| APK debug | `./gradlew assembleDebug` | Dev / piloto técnico |
| APK release | `./gradlew assembleRelease` | Distribución interna |
| AAB release | `./gradlew bundleRelease` | Play Store |

## CI release (manual approval)

Pipeline separado debe: validar versión → tests → prebuild → firmar → AAB → checksums → artifact → release notes → tag.  
**No** publicar a producción sin aprobación manual.

## Verificación local

```bash
apksigner verify --print-certs app-release.apk
shasum -a 256 app-release.aab
```

Hasta configurar secretos CI, los builds release locales usan el keystore de debug o uno inyectado por el operador (fuera del repo).
