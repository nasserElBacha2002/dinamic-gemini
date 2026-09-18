# AGENTS.md — Database / migraciones (local)

Complementa el `AGENTS.md` raíz. Aplicable cuando el repo versiona esquema (SQL, Prisma, Flyway, etc.).

## Descubrí primero

- Dónde viven migraciones forward/rollback y cómo se registran como aplicadas.
- Comando real de migrate / status (package scripts, CLI del ORM, etc.).
- Convenciones de nombres, batches (`GO`, etc.) y transacciones del runner.

## Reglas

- Migraciones idempotentes o defensivas según el estilo del repo.
- Compatibilidad hacia atrás en deploys rolling; preferí add nullable + backfill a drops destructivos.
- Respetá constraints, índices y FKs tenant-scoped si el esquema los usa.
- No DML de negocio en migraciones salvo que el proyecto ya lo haga así.
- No anides transacciones de forma incompatible con el runner.
- No edites datos de producción ni commits de dumps con PII.
- Acompañá cambios de contrato con tests de integración/schema si el repo los tiene.

## Verificación

Aplicá/status con el comando del proyecto en un entorno local. No ejecutes rollback en prod sin autorización.
