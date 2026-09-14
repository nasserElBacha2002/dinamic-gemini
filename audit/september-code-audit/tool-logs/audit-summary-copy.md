# Resumen automático de auditoría

Fecha: 2026-09-14T15:32:23+00:00
Estado general: ERROR
Severidad máxima: high

## Estado general

| Área | Estado | Severidad máxima | Observación |
|---|---|---|---|
| Backend | ERROR | high | Pytest OK passed=5261 |
| Frontend | FINDINGS | medium | Vitest OK passed=1300 |
| Mobile | FINDINGS | high | Jest OK passed=734 |
| Arquitectura backend | FINDINGS | high | Boundary FAIL=2 |
| Arquitectura frontend | FINDINGS | high | Import signals=11 |

## Backend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Ruff | OK | none | issues=0 | audit/raw/backend-ruff.txt |
| Mypy | OK | none | errors=0 | audit/raw/backend-mypy.txt |
| Bandit | FINDINGS | medium | total=174, high=0, medium=102, low=72, blocking_high=0 | audit/raw/backend-bandit.json |
| pip-audit | OK | none | total=0 | audit/raw/backend-pip-audit.json |
| Gitleaks | EXECUTION_ERROR | high | - | audit/raw/backend-gitleaks.json |
| Pytest | OK | none | passed=5261, skipped=4 | audit/raw/backend-pytest.txt |

## Frontend

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| ESLint | FINDINGS | medium | problems=26, errors=0, warnings=26 | audit/raw/frontend-eslint.txt |
| Typecheck | OK | none | ts_errors=0 | audit/raw/frontend-typecheck.txt |
| npm audit | FINDINGS | medium | critical=0, high=0, moderate=2, low=0, info=0, total=2 | audit/raw/frontend-npm-audit.json |
| Vitest | OK | none | failed_files=0, passed_files=224, total_files=224, failed_tests=0, passed_tests=1300, total_tests=1300 | audit/raw/frontend-vitest.txt |
| useEffect audit | FINDINGS | medium | uses=76, files=49 | audit/raw/frontend-useeffects-audit.md |
| Error handling audit | FINDINGS | medium | files=246, try_blocks=118, catch_blocks=80 | audit/raw/frontend-error-handling-audit.md |
| Reusable components audit | FINDINGS | medium | candidate_files=0, button_refs=841 | audit/raw/frontend-reusable-components-audit.md |

## Mobile

| Herramienta | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Typecheck | OK | none | ts_errors=0 | audit/raw/mobile-typecheck.txt |
| ESLint | OK | none | problems=0, errors=0, warnings=0 | audit/raw/mobile-lint.txt |
| Jest | OK | none | failed=0, skipped=0, passed=734, total=734, failed_suites=0, passed_suites=82, total_suites=82 | audit/raw/mobile-jest.txt |
| npm audit | FINDINGS | high | critical=1, high=13, moderate=24, low=2, info=0, total=40 | audit/raw/mobile-npm-audit.json |

## Arquitectura backend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | FINDINGS | high | too_many_args=610, too_many_branches=127, too_many_returns=110, broad_exception=241, unused_import=17, signals=1105 | audit/raw/backend-code-smells.txt |
| Complejidad | FINDINGS | high | grade_c=562, grade_d=124, grade_e=46, grade_f=33 | audit/raw/backend-complexity.txt |
| Límites de imports | FINDINGS | high | fail=2, review=2 | audit/raw/backend-import-boundaries.txt |
| SOLID/GRASP | FINDINGS | medium | signals=12 | audit/raw/backend-solid-grasp-audit.md |

## Arquitectura frontend

| Auditoría | Estado | Severidad | Métricas | Reporte |
|---|---|---|---|---|
| Code smells | FINDINGS | medium | problems=26, errors=0, warnings=26 | audit/raw/frontend-code-smells.txt |
| Complejidad | FINDINGS | high | files_scanned=473, functions_approx=4341, conditional_tokens=1764, files_gt_300=53, files_gt_1000=8 | audit/raw/frontend-complexity.txt |
| Límites de imports | FINDINGS | medium | signals=11 | audit/raw/frontend-import-boundaries.txt |
| Duplicación | SKIPPED | info | - | audit/raw/frontend-duplication.txt |
| Código muerto | FINDINGS | medium | signals=1077 | audit/raw/frontend-dead-code.txt |
| SOLID/React | FINDINGS | medium | signals=6 | audit/raw/frontend-solid-react-audit.md |

## Hallazgos principales automáticos

- Bandit: total=174, high=0, medium=102.
- npm audit frontend: moderate=2, high=0, critical=0.
- Complejidad frontend: files>300=53, files>1000=8.
- Boundaries backend: fail=2, review=2.
- Boundaries frontend: señales heurísticas=11.
- Código muerto frontend: señales=1077 (requiere validación manual).
- Duplicación frontend no cuantificada formalmente (jscpd no disponible).
- useEffect audit: usos=76, archivos=49; revisar posibles falsos negativos.
- Error handling audit: archivos=246, try=118, catch=80.

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
