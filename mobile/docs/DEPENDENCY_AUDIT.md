# Dependencias y vulnerabilidades (Fase 3)

Fecha de revisión: 2026-07-17  
Comando: `cd mobile && npm audit`

## Resumen

`npm audit` reporta vulnerabilidades transitivas típicas del ecosistema Expo 51 / RN 0.74.  
**No** se ejecutó `npm audit fix --force` (rompe peer ranges).

## Clasificación operativa

| Tipo | Acción |
|------|--------|
| Runtime explotable en APK | Revisar caso a caso; actualizar módulo puntual |
| Dev-only (eslint, jest, metro) | Aceptado en piloto; re-auditar en release |
| No aplicable (path no empaquetado) | Documentar y aceptar |

## Stack congelado (piloto)

- Expo ~51
- React Native 0.74.5
- expo-build-properties (min/compile/target SDK 24/34/34)

Actualizaciones mayores de Expo/RN = fase aparte con plan de rollback.
