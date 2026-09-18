# AGENTS.md — Backend / API (local)

Complementa el `AGENTS.md` raíz. Aplicable a módulos de API/servidor cuando existan.

## Descubrí primero

- Layout de capas (routes, controllers, services, repositories, etc.) en este módulo.
- Scripts en su `package.json` / Makefile / `pyproject.toml`: test, lint, typecheck/build, migrate, seed.
- Middleware de auth, autorización y (si hay) tenant/company.
- Jobs/workers: dónde viven, flags de enable, patrón de cola/outbox/lease.

## Reglas

- Seguí el flujo de capas existente; no saltees validación ni auth.
- SQL/ORM: parámetros / query builder del proyecto; nunca concatenar input.
- Transacciones: usá el mecanismo del proyecto; no inventes un patrón de TX distinto.
- Multi-tenant: scope siempre por el identificador de tenant del esquema.
- Jobs: idempotencia, deduplicación, leases/fencing, reintentos y estados ya definidos.
- Integraciones externas: timeouts, reintentos, dedup, rate limits; credenciales solo por env/secret store; no loguear secretos.
- Tests: unit vs integration según convención del repo; fixtures temporales no deben depender de “ahora − N días” si el dominio usa fechas fijas.

## Verificación

Ejecutá los scripts de este módulo descubiertos en inspección. Si falta DB/servicios locales, reportalo.
