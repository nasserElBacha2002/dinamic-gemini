# AGENTS.md — Frontend (local)

Complementa el `AGENTS.md` raíz. Aplicable a apps web/UI cuando existan.

## Descubrí primero

- Framework UI, router, data fetching y formularios reales del módulo.
- Cliente API y dónde viven types/schemas compartidos con el backend.
- Auth, selección de tenant/workspace y guards de ruta/permiso.
- Scripts: `dev`, `lint`, `build`/`typecheck`, `test`.

## Reglas

- La API es fuente de verdad; no inventes campos ni endpoints.
- Reutilizá clientes, hooks, design system y query keys existentes.
- Permisos en UI no sustituyen al backend; manejá 401/403/errores de API.
- Listados/formularios: estados loading / error / empty; feedback en mutaciones.
- Accesibilidad básica: labels en controles; no solo color para errores.
- No agregues librería UI ni state manager global sin pedido explícito.
- No hardcodees secrets ni URLs de API fuera del patrón de env del proyecto.

## Verificación

Lint, build/typecheck y tests del módulo según scripts reales. Reportá omisiones.
