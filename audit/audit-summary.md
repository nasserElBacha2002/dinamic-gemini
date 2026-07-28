# Resumen automático de auditoría

Fecha: 2026-07-28T14:09:38+00:00
Estado general: FINDINGS
Severidad máxima: high

## Estado general

| Área | Estado | Severidad máxima | Observación |
|---|---|---|---|
| Backend | FINDINGS | medium | Pytest OK passed=3797 |
| Frontend | FINDINGS | medium | Vitest OK passed=1217 |
| Mobile | FINDINGS | high | Jest OK passed=320 |
| Arquitectura backend | NOT_RUN | none | Sin FAIL de boundaries |
| Arquitectura frontend | NOT_RUN | none | Sin señales fuertes de acoplamiento |

## Backend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Ruff | OK | none | issues=0 | audit/raw/backend-ruff.txt |
| Mypy | OK | none | errors=0 | audit/raw/backend-mypy.txt |
| Bandit | FINDINGS | medium | total=92, high=0, medium=54, low=38 | audit/raw/backend-bandit.json |
| pip-audit | OK | none | total=0 | audit/raw/backend-pip-audit.json |
| Pytest | OK | none | passed=3797, skipped=44 | audit/raw/backend-pytest.txt |

## Frontend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| ESLint | FINDINGS | medium | problems=21, errors=0, warnings=21 | audit/raw/frontend-eslint.txt |
| Typecheck | OK | none | ts_errors=0 | audit/raw/frontend-typecheck.txt |
| npm audit | FINDINGS | medium | critical=0, high=0, moderate=2, low=0, info=0, total=2 | audit/raw/frontend-npm-audit.json |
| Vitest | OK | none | failed_files=0, passed_files=203, total_files=203, failed_tests=0, passed_tests=1217, total_tests=1217 | audit/raw/frontend-vitest.txt |
| useEffect audit | FINDINGS | medium | uses=64, files=41 | audit/raw/frontend-useeffects-audit.md |
| Error handling audit | FINDINGS | medium | files=224, try_blocks=88, catch_blocks=61 | audit/raw/frontend-error-handling-audit.md |
| Reusable components audit | FINDINGS | medium | candidate_files=0, button_refs=650 | audit/raw/frontend-reusable-components-audit.md |

## Mobile

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Typecheck | OK | none | ts_errors=0 | audit/raw/mobile-typecheck.txt |
| ESLint | OK | none | problems=0, errors=0, warnings=0 | audit/raw/mobile-lint.txt |
| Jest | OK | none | failed=0, skipped=0, passed=320, total=320, failed_suites=0, passed_suites=45, total_suites=45 | audit/raw/mobile-jest.txt |
| npm audit | FINDINGS | high | critical=1, high=62, moderate=12, low=1, info=0, total=76 | audit/raw/mobile-npm-audit.json |

## Arquitectura backend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | NOT_RUN | none | - | audit/raw/backend-code-smells.txt |
| Complejidad | NOT_RUN | none | - | audit/raw/backend-complexity.txt |
| Límites de imports | NOT_RUN | none | - | audit/raw/backend-import-boundaries.txt |
| SOLID/GRASP | NOT_RUN | none | - | audit/raw/backend-solid-grasp-audit.md |

## Arquitectura frontend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | NOT_RUN | none | - | audit/raw/frontend-code-smells.txt |
| Complejidad | NOT_RUN | none | - | audit/raw/frontend-complexity.txt |
| Límites de imports | NOT_RUN | none | - | audit/raw/frontend-import-boundaries.txt |
| Duplicación | NOT_RUN | none | - | audit/raw/frontend-duplication.txt |
| Código muerto | NOT_RUN | none | - | audit/raw/frontend-dead-code.txt |
| SOLID/React | NOT_RUN | none | - | audit/raw/frontend-solid-react-audit.md |

## Hallazgos principales automáticos

- Bandit: total=92, high=0, medium=54.
- npm audit frontend: moderate=2, high=0, critical=0.
- Complejidad frontend: files>300=0, files>1000=0.
- Boundaries backend: fail=0, review=0.
- Duplicación frontend no cuantificada formalmente (jscpd no disponible).
- useEffect audit: usos=64, archivos=41; revisar posibles falsos negativos.
- Error handling audit: archivos=224, try=88, catch=61.

## Recomendación automática de prioridad

1. Tests críticos
2. Seguridad/dependencias
3. Tipado
4. Arquitectura
5. Code smells
6. Limpieza/ruido

## Limitaciones

- Esta consolidación es automática y puede requerir revisión humana.
- Los principios SOLID/GRASP/React se interpretan como señales heurísticas.
- Algunos reportes pueden depender de herramientas instaladas localmente.
- No implica corrección automática.
