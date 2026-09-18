# AGENTS.md — Mobile (local)

Complementa el `AGENTS.md` raíz. Aplicable a la app móvil cuando exista.

## Descubrí primero

- Stack nativo/híbrido real del módulo (scripts en su `package.json`).
- Persistencia local, sync/offline y workers de upload si existen.
- Auth, selección de tenant/workspace y límites de conectividad.
- Scripts: `start`, `lint`, `typecheck`, `test` / `verify`, builds de plataforma.

## Reglas

- Asumí conectividad intermitente: reintentos, colas locales e idempotencia según el código existente.
- No inventes APIs ni campos; el backend es fuente de verdad.
- Respetá compatibilidad de plataforma (Android/iOS) y el patrón de env del módulo.
- No agregues SDKs ni librerías nativas sin pedido explícito.
- No loguees tokens ni secretos; no hardcodees URLs fuera del patrón del proyecto.
- Permisos/UI no sustituyen autorización del servidor.

## Verificación

Lint, typecheck y tests del módulo según scripts reales. Reportá omisiones (emulador/device).
