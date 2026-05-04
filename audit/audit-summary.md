# Resumen automático de auditoría

Fecha: 2026-04-29T22:03:15+00:00
Estado general: ERROR
Severidad máxima: critical

## Estado general

| Área | Estado | Severidad máxima | Observación |
|---|---|---|---|
| Backend | ERROR | high | Sin fallos críticos detectados |
| Frontend | FINDINGS | critical | Tests fallidos frontend=86 |
| Arquitectura backend | FINDINGS | high | Boundary FAIL=1 |
| Arquitectura frontend | FINDINGS | high | Import signals=8 |

## Backend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Ruff | FINDINGS | medium | issues=3552, fixable=828 | audit/raw/backend-ruff.txt |
| Mypy | FINDINGS | high | errors=80, files=35 | audit/raw/backend-mypy.txt |
| Bandit | FINDINGS | high | total=59, high=1, medium=35, low=23 | audit/raw/backend-bandit.json |
| pip-audit | OK | none | total=0 | audit/raw/backend-pip-audit.json |
| Pytest | ERROR | medium | collected=1785 | audit/raw/backend-pytest.txt |

## Frontend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| ESLint | FINDINGS | high | problems=66, errors=40, warnings=26 | audit/raw/frontend-eslint.txt |
| Typecheck | OK | none | ts_errors=0 | audit/raw/frontend-typecheck.txt |
| npm audit | FINDINGS | medium | critical=0, high=0, moderate=7, low=0, info=0, total=7 | audit/raw/frontend-npm-audit.json |
| Vitest | FINDINGS | critical | failed_files=19, passed_files=49, total_files=68, failed_tests=86, passed_tests=340, total_tests=426 | audit/raw/frontend-vitest.txt |
| useEffect audit | FINDINGS | medium | uses=46, files=20 | audit/raw/frontend-useeffects-audit.md |
| Error handling audit | FINDINGS | medium | files=100, try_blocks=59, catch_blocks=25 | audit/raw/frontend-error-handling-audit.md |
| Reusable components audit | FINDINGS | medium | candidate_files=0, button_refs=332 | audit/raw/frontend-reusable-components-audit.md |

## Arquitectura backend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | FINDINGS | high | too_many_args=118, too_many_branches=25, too_many_returns=20, broad_exception=85, unused_import=42, signals=290 | audit/raw/backend-code-smells.txt |
| Complejidad | FINDINGS | high | grade_c=124, grade_d=27, grade_e=8, grade_f=4 | audit/raw/backend-complexity.txt |
| Límites de imports | FINDINGS | high | fail=1, review=2 | audit/raw/backend-import-boundaries.txt |
| SOLID/GRASP | FINDINGS | medium | signals=12 | audit/raw/backend-solid-grasp-audit.md |

## Arquitectura frontend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | FINDINGS | high | problems=66, errors=40, warnings=26 | audit/raw/frontend-code-smells.txt |
| Complejidad | FINDINGS | high | files_scanned=183, functions_approx=1513, conditional_tokens=808, files_gt_300=19, files_gt_1000=4 | audit/raw/frontend-complexity.txt |
| Límites de imports | FINDINGS | medium | signals=8 | audit/raw/frontend-import-boundaries.txt |
| Duplicación | SKIPPED | info | - | audit/raw/frontend-duplication.txt |
| Código muerto | FINDINGS | medium | signals=470 | audit/raw/frontend-dead-code.txt |
| SOLID/React | FINDINGS | medium | signals=6 | audit/raw/frontend-solid-react-audit.md |

## Hallazgos principales automáticos

- Frontend vitest reporta 86 tests fallidos.
- Bandit: total=59, high=1, medium=35.
- npm audit frontend: moderate=7, high=0, critical=0.
- Mypy backend detecta 80 errores en 35 archivos.
- Complejidad frontend: files>300=19, files>1000=4.
- Boundaries backend: fail=1, review=2.
- Boundaries frontend: señales heurísticas=8.
- Código muerto frontend: señales=470 (requiere validación manual).
- Duplicación frontend no cuantificada formalmente (jscpd no disponible).
- useEffect audit: usos=46, archivos=20; revisar posibles falsos negativos.
- Error handling audit: archivos=100, try=59, catch=25.
- Ruff backend: issues=3552, fixable=828.

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
