# AGENTS.md (local)

Instrucciones locales para agentes de IA. **No versionar** (ver `.gitignore`). Los `AGENTS.md` anidados complementan este archivo.

Plantilla multi-proyecto: descubrí stack, scripts y convenciones **en este repo**; no inventes lo que no exista.

## Inspección previa (obligatoria)

Antes de cambiar código:

1. Revisá estructura, `package.json` / manifiestos, CI (`.github/`, etc.), README y docs del repo.
2. Identificá comandos reales de test, lint, typecheck, build y migraciones.
3. Leé el código, tests y migraciones **relacionados** al cambio.
4. Preferí el código vigente si diverge de la documentación.

## Comportamiento del agente

- Respetá arquitectura, capas y contratos existentes; reutilizá servicios, repos, componentes y utilidades.
- No inventes APIs, comportamientos, frameworks ni capas nuevas sin pedido explícito.
- Mantené el alcance solicitado; sin refactors oportunistas.
- No modifiques secretos (`.env`, credenciales), lockfiles salvo pedido, artefactos generados ni config de deploy ajena.
- Preservá cambios locales del usuario; no reviertas trabajo no relacionado.
- Identificá supuestos; pedí aclaración solo si son **bloqueantes**.
- Preservá compatibilidad hacia atrás salvo requerimiento explícito o cambio versionado.
- Considerá permisos, validación, errores y casos límite como en el código vecino.
- Cuando aplique: idempotencia, concurrencia, locking, transacciones, leases/outbox.
- Si el proyecto es multi-tenant / multi-cliente, mantené aislamiento en queries y mutaciones.
- Agregá o actualizá pruebas relevantes al comportamiento cambiado.
- Ejecutá **solo** comandos descubiertos en el repo o CI.
- No declares éxito si fallan tests, typecheck, lint o build ejecutados.
- Informá verificaciones omitidas y el motivo.
- Antes de cerrar: `git status` y `git diff` (sin pisar cambios ajenos).
- Sin `commit`, `push`, reset destructivo, amend forzado ni deploy sin autorización explícita.

## Anidados (opcional)

Creá o mantené `AGENTS.md` solo en módulos que aporten reglas distintas (p. ej. `backend/`, `frontend/`, `mobile/`, `backend/src/database/`). No dupliques este archivo.

## Al finalizar

1. Verificá con los scripts reales del área tocada.
2. Listá archivos tocados, riesgos y lo no verificado.
´