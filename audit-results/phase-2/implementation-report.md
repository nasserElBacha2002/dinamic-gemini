# Phase 2 — Implementation Report

## 1. Estado

`IMPLEMENTED_AND_VALIDATED` (mergeable to `main`; Phase 3 not started).

## 2. Causas raíz

1. Frontend treated list order / `jobs[0]` as operational SoT and always sent `job_id`, forcing explicit mode.
2. Inventory-rooted uploads/CRUD lacked actor→client scope (UUID alone was enough for any JWT admin).
3. `MEMORY_FALLBACK` / quiet `MEMORY_ONLY` could activate in hosted or unknown environments; health did not expose backend mode.

## 3–4. Flujo anterior vs nuevo

**Antes:** FE podía pinnear el primer job; analytics memoria sumaba todas las corridas; uploads sin scope de cliente; fallback memoria posible vía env override en production.

**Ahora:** FE usa `resolveBrowseRunJobIds` (URL → operational display → omit API `job_id`); backend `ResultContextResolver` único; analytics memoria = slice operacional; uploads autorizan client scope antes del spool; memoria prohibida fuera de test/local/dev.

## 5–7. Contrato / precedencia / legacy

Ver `result-context-contract.md`. Legacy = `job_id IS NULL` cuando no hay operacional; no hay auto-latest.

## 8–11. Cambios

- **Backend:** `inventory_access`, `require_inventory_client_scope`, upload/list/delete/process wiring, memory policy + health fields, memory analytics slice.
- **Frontend:** `resolveBrowseRunJobId`, `AislePositionsPage`, `AisleRunSelector`, export usa `visibleJobId`.
- **Exports/analytics:** mismo contexto resuelto (positions + memory analytics operational slice).

## 12–14. Autorización / matriz / IDOR

Ver `upload-authorization-matrix.md` y `security-test-report.md`. Política 404 on cross-client mismatch (no leak).

## 15–18. Cleanup / SQL-memory / fail-fast / health

Upload rechazado no escribe storage. Fail-fast en probe/config prohibidos. Health: `repository_backend`, `repository_backend_environment`, `fallback_activated`.

## 19. Migraciones

Ninguna (ver `migration-validation.md`).

## 20–21. Tests / resultados

- Backend: **3840 passed**, 47 skipped.
- Frontend SoT tests: **41 passed**.
- Mobile: typecheck/lint/jest OK.
- Ruff: All checks passed.
- Quality Gate `--strict`: **PASS**.

## 22–24. Limitaciones / riesgos / alcance

- No todos los endpoints inventory-rooted (solo uploads/assets/process + staging) tienen el gate nuevo; inventory list/CRUD preexistente puede necesitar Fase posterior si aún falta scope.
- Capture staging autoriza inventory scope en ruta; use case aún no recibe `access_user` (defense in depth parcial).
- Fase 3 (fencing, Bandit deep, etc.) **no iniciada**.

## 25. Mergeabilidad

Sí — cambios acotados a Fase 2, tests verdes, gate PASS.
