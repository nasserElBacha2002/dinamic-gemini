# 00 — Executive summary

| Field | Value |
|-------|-------|
| Product | Dinamic Gemini / Dinamic Inventory (physical inventory via images, codes, labels, TXT) |
| Audit phase | FASE 1 — code audit (read-only) |
| Commit | `219b88bcae1181a0b434425efe48b5fa2c70f3b3` |
| Branch | `DIN-357` |
| Started (UTC) | 2026-09-14T15:26:26Z (baseline) / tools 2026-09-14T15:26:49Z |
| Finished (UTC) | 2026-09-14T15:34:00Z (approx) |
| Verdict | **READY_WITH_FINDINGS** |

## Estado general

El repositorio es un monorepo maduro (backend FastAPI + SQL Server, frontend React, mobile Expo, workers, pipeline CODE_SCAN/Vision). La suite oficial `scripts/audit/run_full_audit.sh` se ejecutó (`run_id=20260914T152649Z`). El quality gate estricto terminó en **FAIL** por: (1) gitleaks vía Docker `EXECUTION_ERROR` (exit 126, sin acceso al daemon Docker en este entorno); (2) ausencia de `audit/security-exceptions.json`.

Validaciones duras de calidad (ruff, mypy, pytest, typecheck FE/mobile, vitest, jest, lint mobile) pasaron. Hallazgos de seguridad manuales HIGH (aislamiento tenant incompleto bajo `company_admin`, refresh tokens in-memory, tokens en `localStorage`) y dependencias mobile (1 critical / 13 high en npm audit) quedan registrados sin remediación en esta fase.

Un escaneo gitleaks **alternativo** con binario host `gitleaks 8.30.1` reportó **0 leaks** (PASS), pero no sustituye el collector oficial con imagen pinned.

## Alcance

- Incluido: backend, frontend, mobile, contracts, scripts/audit, CI workflows, docs de arquitectura/calidad, auth, uploads/imports, jobs, reconocimiento, TXT/ZIP/CSV.
- Excluido (fase 2+): inventario formal de todos los endpoints DAST, ejecución DAST activa/mutante, migraciones sobre DB compartida, ataques a servicios desplegados.
- No es Dinamic Attendance; no se auditó WhatsApp/Twilio/asistencias.

## Componentes auditados

Backend API/worker/pipeline, frontend SPA, mobile Android/Expo, SQL migrations (inspección), artifact storage builders, auth JWT, scripts de quality gate/audit, `security-audit.yaml` (config only).

## Comandos ejecutados (resumen)

| Comando | Resultado |
|---------|-----------|
| `bash scripts/audit/run_full_audit.sh` | FAIL (gate); collectors mayormente OK |
| Host `gitleaks detect` (fallback) | PASS (0 leaks) |
| `npm audit --audit-level=high` (frontend) | PASS (solo moderate) |
| `npm audit --audit-level=high` (mobile) | FAIL (high/critical) |
| Docker gitleaks oficial | BLOCKED (docker.sock) |
| DAST / Semgrep via security-agents | NOT_CONFIGURED / not run |
| Release scanners / smoke SQL | NOT_RUN (infra / costo) |

## Hallazgos por severidad (registro humano)

| Severidad | Cantidad |
|-----------|----------|
| CRITICAL | 0 (ninguno demostrado como explotable en runtime sin más pruebas) |
| HIGH | 6 (SEC-001, SEC-002, SEC-003, SEC-006, TEST-002, TEST-003) |
| MEDIUM | 8 |
| LOW | 5 |
| INFO | 6 |

## Hallazgos por categoría

| Categoría | Cantidad |
|-----------|----------|
| Seguridad | 7 |
| Arquitectura | 4 |
| Funcional / producto | 5 |
| Testing | 3 |
| Operativo / tooling | 4 |
| Dependencias | 2 |

## Principales riesgos

1. **Multi-tenancy incompleta** cuando existe `company_admin` con `client_id`: list/get inventarios y clientes sin `InventoryAccessPolicy` (IDOR potencial). Confianza: VERIFIED en código; explotabilidad depende de que se activen principals scoped.
2. **Refresh tokens solo en memoria de proceso** — pérdida al restart / multi-instancia.
3. **Tokens JWT en `localStorage` del frontend** — exposición XSS.
4. **Dependencias mobile** con advisory critical (`tar`) y 13 high — alcance mayormente toolchain Expo/Metro (INFERRED reachability limitada en runtime de captura).
5. **OpenAPI/Swagger por defecto** en FastAPI sin `docs_url=None`.

## Bloqueos

- Gitleaks oficial (Docker) **BLOCKED** en este entorno.
- `audit/security-exceptions.json` **ausente** → gate falla siempre.
- DAST activo / Semgrep / CodeQL / Trivy-in-SAST framework **no ejecutados** (requieren security-agents + API local + DB disposable).

## Recomendación de avance

Avanzar a **FASE 2 (inventario formal de endpoints + plan SAST/DAST)** con los hallazgos HIGH como backlog prioritario. No declarar “listo para producción multi-tenant” hasta cerrar aislamiento AuthZ y el gate de excepciones/secretos.

**No se implementaron correcciones en esta fase.**
