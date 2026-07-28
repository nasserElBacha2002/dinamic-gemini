# Phase 2 — Implementation Report

## 1. Estado

`CORRECTIONS_APPLIED` — Phase 2 review findings closed; Phase 1 SQL IT executed locally.
See also `implementation-corrections.md`. Phase 3 not started.

## 2. Causas raíz

1. Frontend treated list order / `jobs[0]` as operational SoT and always sent `job_id`, forcing explicit mode.
2. Inventory-rooted uploads/CRUD lacked actor→client scope (UUID alone was enough for any JWT admin); application auth was optional.
3. `MEMORY_FALLBACK` / quiet `MEMORY_ONLY` could activate in hosted or unknown environments; health used private resolution and readiness ignored SQL policy.

## 3–4. Flujo anterior vs nuevo

**Antes:** FE podía pinnear el primer job; analytics memoria sumaba todas las corridas; uploads sin scope de cliente; fallback memoria posible vía env override en production; use cases aceptaban `AuthUser | None`.

**Ahora:** FE usa `resolveBrowseRunJobIds` (URL → operational display → omit API `job_id`); backend `ResultContextResolver` único; analytics memoria = slice operacional; uploads/process/capture staging requieren `AccessPrincipal` + `InventoryAccessPolicy`; memoria prohibida fuera de test/local/dev; `/ready` falla si SQL obligatorio no está disponible.

## 5–7. Contrato / precedencia / legacy

Ver `result-context-contract.md`. Legacy = `job_id IS NULL` cuando no hay operacional; no hay auto-latest.

## 8–11. Cambios

- **Backend:** `AccessPrincipal`, `InventoryAccessPolicy`, `require_capture_session_upload_scope`, `RepositoryBackendStatus`, health/ready, memory aliases, SQL cleanup FK order for IT.
- **Frontend:** `resolveBrowseRunJobIds`, `visibleJobId` / explicit / operational (sin `jobs[0]`).
- **Exports/analytics/evidence:** mismo contexto vía `ResultContextResolver`.

## 12–14. Autorización / matriz / IDOR

Ver `upload-authorization-matrix.md` y `security-test-report.md`. Política 404 on cross-client mismatch (no leak).

## 15–18. Cleanup / SQL-memory / fail-fast / health

Upload rechazado no escribe storage (application spool instrumentado en tests). Fail-fast en probe/config prohibidos. Health: resolved/healthy/reason_code vía API pública.

## 19. Migraciones

Ninguna nueva en Fase 2. Fase 1: `0071` validada en SQL IT (ver `implementation-corrections.md`).

## 20–21. Tests / resultados

Registrar resultados finales en dumps `implementation-corrections-*.txt` (gitignored) y en `implementation-corrections.md`.

## 22–24. Limitaciones / riesgos / alcance

Ver `implementation-corrections.md` §Limitaciones.
- No todos los endpoints inventory-rooted (solo uploads/assets/process + staging) tienen el gate nuevo; inventory list/CRUD preexistente puede necesitar Fase posterior si aún falta scope.
- Capture staging autoriza inventory scope en ruta; use case aún no recibe `access_user` (defense in depth parcial).
- Fase 3 (fencing, Bandit deep, etc.) **no iniciada**.

## 25. Mergeabilidad

Sí — cambios acotados a Fase 2, tests verdes, gate PASS.
