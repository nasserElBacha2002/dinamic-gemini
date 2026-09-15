# 11 — Prioritized remediation roadmap (no implementation)

## P0 — Quick wins / gate hygiene

| Item | Deps | Riesgo regresión | Aceptación |
|------|------|------------------|------------|
| Crear `audit/security-exceptions.json` válido (vacío o baseline firmado) | Ninguna | Bajo | Gate deja de fallar por archivo missing |
| Asegurar gitleaks en CI con Docker o binario pinned | CI | Bajo | Collector ≠ EXECUTION_ERROR |
| Corregir `.gitleaksignore` fingerprint inválido | Ninguna | Ninguno | Warning desaparece |

## P1 — Seguridad AuthZ/AuthN

| Item | Deps | Riesgo | Aceptación |
|------|------|--------|------------|
| Aplicar `InventoryAccessPolicy` a list/get inventarios, metrics, exports | SEC-001 | Medio (cambiar visibilidad) | company_admin solo ve su client; tests IDOR verdes |
| Scope clients list/get | SEC-002 | Medio | Igual |
| Persistencia refresh tokens (SQL/Redis) o documentar single-instance | SEC-003 | Medio | Refresh ok tras restart / 2 workers |
| Matriz tests company_admin | TEST-002 | Bajo | Coverage AuthZ |

## P2 — Cliente / superficie

| Item | Aceptación |
|------|------------|
| Reducir exposición OpenAPI en prod | `/docs` 404 o auth |
| Mitigar tokens localStorage (o CSP/XSS hardening) | Threat model actualizado |
| Triage mobile npm critical/high (overrides) | `npm audit --audit-level=high` exit 0 o exceptions firmadas |

## P3 — Arquitectura / deuda

| Item | Aceptación |
|------|------------|
| Romper ARCH-001/002 imports | Architecture audit R1/R2 PASS |
| Split `aisles.py` | Archivos < umbral equipo |
| Documentar offline aisle=ZIP-only | Docs + mobile UX alineados |
| Decidir review-queue FE vs API | Una superficie |

## P4 — Fase 2 preparativos

- Inventario formal endpoints
- Seed DB disposable + security-agents DAST non-mutating
- SAST Semgrep con rules_path local (sin downloads si policy lo exige)

## No hacer aún

- Refactors masivos pipeline
- Mutating DAST en DB compartida
- “Fix all bandit medium”
