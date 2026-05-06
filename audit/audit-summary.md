# Resumen automático de auditoría

Fecha: 2026-05-06T12:52:14+00:00
Estado general: ERROR
Severidad máxima: critical

## Estado general

| Área | Estado | Severidad máxima | Observación |
|---|---|---|---|
| Backend | ERROR | critical | Tests fallidos backend=3 |
| Frontend | ERROR | critical | Tests fallidos frontend=17 |
| Arquitectura backend | FINDINGS | high | Sin FAIL de boundaries |
| Arquitectura frontend | FINDINGS | high | Import signals=8 |

## Backend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Ruff | ERROR | low | - | audit/raw/backend-ruff.txt |
| Mypy | FINDINGS | high | errors=8, files=8 | audit/raw/backend-mypy.txt |
| Bandit | FINDINGS | low | total=17, high=0, medium=0, low=17 | audit/raw/backend-bandit.json |
| pip-audit | OK | none | total=0 | audit/raw/backend-pip-audit.json |
| Pytest | FINDINGS | critical | collected=1842, failed=3, passed=1826, skipped=13 | audit/raw/backend-pytest.txt |

## Frontend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| ESLint | ERROR | low | - | audit/raw/frontend-eslint.txt |
| Typecheck | OK | none | ts_errors=0 | audit/raw/frontend-typecheck.txt |
| npm audit | FINDINGS | medium | critical=0, high=0, moderate=7, low=0, info=0, total=7 | audit/raw/frontend-npm-audit.json |
| Vitest | FINDINGS | critical | failed_files=7, passed_files=61, total_files=68, failed_tests=17, passed_tests=409, total_tests=426 | audit/raw/frontend-vitest.txt |
| useEffect audit | FINDINGS | medium | uses=17, files=12 | audit/raw/frontend-useeffects-audit.md |
| Error handling audit | FINDINGS | medium | files=107, try_blocks=65, catch_blocks=31 | audit/raw/frontend-error-handling-audit.md |
| Reusable components audit | FINDINGS | medium | candidate_files=0, button_refs=332 | audit/raw/frontend-reusable-components-audit.md |

## Arquitectura backend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | FINDINGS | high | too_many_args=122, too_many_branches=13, too_many_returns=12, broad_exception=85, unused_import=8, signals=240 | audit/raw/backend-code-smells.txt |
| Complejidad | FINDINGS | high | grade_c=124, grade_d=18, grade_e=3, grade_f=2 | audit/raw/backend-complexity.txt |
| Límites de imports | FINDINGS | medium | fail=0, review=2 | audit/raw/backend-import-boundaries.txt |
| SOLID/GRASP | FINDINGS | medium | signals=12 | audit/raw/backend-solid-grasp-audit.md |

## Arquitectura frontend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | SKIPPED | info | - | audit/raw/frontend-code-smells.txt |
| Complejidad | FINDINGS | high | files_scanned=192, functions_approx=1529, conditional_tokens=800, files_gt_300=19, files_gt_1000=4 | audit/raw/frontend-complexity.txt |
| Límites de imports | FINDINGS | medium | signals=8 | audit/raw/frontend-import-boundaries.txt |
| Duplicación | SKIPPED | info | - | audit/raw/frontend-duplication.txt |
| Código muerto | FINDINGS | medium | signals=470 | audit/raw/frontend-dead-code.txt |
| SOLID/React | FINDINGS | medium | signals=6 | audit/raw/frontend-solid-react-audit.md |

## Hallazgos principales automáticos

- Backend pytest reporta 3 tests fallidos.
- Frontend vitest reporta 17 tests fallidos.
- Bandit: total=17, high=0, medium=0.
- npm audit frontend: moderate=7, high=0, critical=0.
- Mypy backend detecta 8 errores en 8 archivos.
- Complejidad frontend: files>300=19, files>1000=4.
- Boundaries backend: fail=0, review=2.
- Boundaries frontend: señales heurísticas=8.
- Código muerto frontend: señales=470 (requiere validación manual).
- Duplicación frontend no cuantificada formalmente (jscpd no disponible).
- useEffect audit: usos=17, archivos=12; revisar posibles falsos negativos.
- Error handling audit: archivos=107, try=65, catch=31.

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

## F9 — Dependencias frontend (cierre manual, 2026-05-06)

**Estado:** `npm audit` en `frontend/` queda en **0 vulnerabilidades** tras actualización controlada (Vite 6.4.2, Vitest 3.2.4, `postcss` / `yaml` / TypeScript / `eslint-plugin-sonarjs` en `devDependencies`). Evidencia: `audit/raw/frontend-npm-audit-f9-before.json` (7 moderadas) vs `audit/raw/frontend-npm-audit-f9-after.json` (0). Validación: `typecheck`, `lint`, `test -- --run`, `build` OK. Detalle y excepciones: `audit/audit-backlog.md` (sección F9).
