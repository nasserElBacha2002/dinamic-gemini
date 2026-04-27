# Auditoría técnica inicial

Fecha: 2026-04-27
Rama: N/A (workspace sin metadata git disponible)
Commit: N/A
Ejecutor: Quality Gate local

## Objetivo

Consolidar evidencia técnica de calidad, seguridad, pruebas y arquitectura sin corregir hallazgos todavía.

## Alcance

Se analizaron reportes de `audit/raw/` para:
- Backend operativo
- Frontend operativo
- Arquitectura backend
- Arquitectura frontend

## Estado general consolidado

| Área | Estado | Severidad máxima | Riesgo principal | Observación |
|---|---|---|---|---|
| Backend | Detectado | Crítico | 94 tests fallidos en suites core | Deuda fuerte en tests, lint y tipado |
| Frontend | Detectado | Alto | 86 tests fallidos y 7 vulnerabilidades moderadas | Inestabilidad funcional en UI y deuda de hooks |
| Arquitectura backend | Detectado | Alto | Complejidad y acoplamiento en capas | 1 violación FAIL de boundaries + rutas API sobrecargadas |
| Arquitectura frontend | Detectado | Alto | Componentes grandes y acoplamiento UI-servicios | Heurísticas detectan 23 señales de imports sospechosos |
| Dependencias | Detectado | Alto | Vulnerabilidades/modo de auditoría parcial | Frontend con 7 moderadas; backend sin CVE pero con limitación PyPI |
| Tests | Detectado | Crítico | Red de regresión inestable | Backend y frontend con fallos relevantes en flujos principales |

## Resumen backend

| Herramienta | Reporte | Estado | Severidad | Cantidad aprox | Observaciones |
|---|---|---|---|---:|---|
| Ruff | `audit/raw/backend-ruff.txt` | Detectado | Medio | 3545 | Alto volumen de deuda de estilo/calidad; 829 fixables directos |
| Mypy | `audit/raw/backend-mypy.txt` | Detectado | Alto | 80 | Errores en 35 archivos, incluyendo contratos y stubs faltantes |
| Bandit | `audit/raw/backend-bandit.json` | Detectado | Alto | 59 | 1 HIGH, 35 MEDIUM, 23 LOW |
| pip-audit | `audit/raw/backend-pip-audit.json` | Detectado | Informativo | 0 CVE | Sin vulnerabilidades conocidas; paquete local no auditable en PyPI |
| Pytest | `audit/raw/backend-pytest.txt` | Detectado | Crítico | 94 fallos | 1785 tests corridos (1678 pass, 13 skip) |

## Resumen frontend

| Herramienta/Auditoría | Reporte | Estado | Severidad | Cantidad aprox | Observaciones |
|---|---|---|---|---:|---|
| ESLint | `audit/raw/frontend-eslint.txt` | Detectado | Medio | 66 | 40 errores y 26 warnings; foco en hooks |
| Typecheck | `audit/raw/frontend-typecheck.txt` | OK | - | 0 | `tsc --noEmit` sin errores |
| npm audit | `audit/raw/frontend-npm-audit.json` | Detectado | Medio | 7 | 7 moderadas (vite/vitest/esbuild/postcss/yaml) |
| Vitest | `audit/raw/frontend-vitest.txt` | Detectado | Alto | 86 fallos | 19 archivos fallidos (de 68) |
| useEffect audit | `audit/raw/frontend-useeffects-audit.md` | Detectado | Medio | 46 usos | 20 archivos con `useEffect`; varios patrones en 0 |
| Error handling audit | `audit/raw/frontend-error-handling-audit.md` | Detectado | Medio | 100 archivos | Señales amplias de manejo de errores, requiere priorización |
| Reusable components audit | `audit/raw/frontend-reusable-components-audit.md` | Detectado | Medio | 0 / 300+ refs | 0 candidatos pero alta referencia de componentes base |

## Resumen arquitectura backend

| Auditoría | Reporte | Estado | Severidad | Observaciones |
|---|---|---|---|---|
| Code smells | `audit/raw/backend-code-smells.txt` | Detectado | Alto | Pylint reporta too-many-*, unused-import y broad-exception |
| Complejidad | `audit/raw/backend-complexity.txt` | Detectado | Alto | Funciones con grado D y múltiples C en pipeline/orquestación |
| Límites de imports | `audit/raw/backend-import-boundaries.txt` | Detectado | Alto | 1 FAIL (application->api), 2 REVIEW, 5 rutas API sospechosas |
| SOLID/GRASP | `audit/raw/backend-solid-grasp-audit.md` | Detectado | Medio | Evaluación heurística con señales claras de refactor futuro |

## Resumen arquitectura frontend

| Auditoría | Reporte | Estado | Severidad | Observaciones |
|---|---|---|---|---|
| Code smells | `audit/raw/frontend-code-smells.txt` | Detectado | Alto | ESLint + heurística; hallazgos react-hooks y set-state-in-effect |
| Complejidad | `audit/raw/frontend-complexity.txt` | Detectado | Alto | 183 archivos, 1513 funciones aprox, 808 condicionales |
| Límites de imports | `audit/raw/frontend-import-boundaries.txt` | Detectado | Medio | Señales de components con imports API/fetch directo |
| Duplicación | `audit/raw/frontend-duplication.txt` | Detectado | Informativo | `jscpd` no instalado; fallback por patrones de nombres |
| Código muerto | `audit/raw/frontend-dead-code.txt` | Detectado | Medio | `ts-prune` reporta alto volumen de exports potencialmente no usados |
| SOLID/React | `audit/raw/frontend-solid-react-audit.md` | Detectado | Medio | Evaluación heurística de SRP, DIP y patrones React |

## Hallazgos clave consolidados

- Backend presenta **94 tests fallidos** en áreas core de operación de inventario/pipeline.
- Frontend presenta **86 tests fallidos** en suites clave (`ExecutionLogPanel`, `CompareRunsPage`, `MetricsPage`, `InventoryDetailPage`).
- Bandit reporta **1 hallazgo HIGH** y **35 MEDIUM**; principal riesgo en SQL dinámico y manejo de excepciones.
- Mypy reporta **80 errores en 35 archivos**, con riesgo de contratos inconsistentes.
- Ruff reporta **3545 issues**, indicando deuda técnica estructural.
- npm audit frontend reporta **7 vulnerabilidades moderadas** en toolchain.
- Arquitectura backend detecta **violación de boundary** (`application` importando `api`) y rutas API extensas.
- Arquitectura frontend detecta **acoplamiento UI->API/fetch** en componentes.
- Auditoría de complejidad frontend identifica archivos de **>1000 líneas** (`MetricsPage`, `api/client`).
- `ts-prune` detecta alta cantidad de exports potencialmente no usados (requiere validación manual).
- Auditorías heurísticas (`SOLID/GRASP`, `SOLID/React`, scanners textuales) aportan señales, no pruebas definitivas.
- Warning recurrente `npm Unknown env config "devdir"` genera ruido operativo en reportes.

## Riesgos consolidados

### Riesgos críticos

- Inestabilidad de pruebas backend y frontend que compromete la confianza de regresión.

### Riesgos altos

- Hallazgos de seguridad (Bandit HIGH/MEDIUM) y vulnerabilidades moderadas de dependencias frontend.
- Errores de tipado backend con impacto potencial en contratos y runtime.
- Complejidad alta en orquestadores/páginas críticas que eleva probabilidad de defectos.

### Riesgos medios

- Deuda extensa de lint/code smells en backend y frontend.
- Acoplamiento arquitectónico entre capas (backend y frontend).
- Detección de posible código muerto sin clasificación por criticidad.

### Riesgos bajos / informativos

- Limitaciones de tooling instalado parcialmente (jscpd/import tooling según entorno).
- Warnings de entorno npm (`devdir`) que afectan legibilidad de ejecuciones.

## Limitaciones de la auditoría

- SOLID/GRASP y SOLID/React se evaluaron de forma **heurística**, no como verificación formal.
- Algunos scanners producen falsos positivos/falsos negativos.
- Varios resultados dependen de herramientas instaladas en entorno local.
- Sin `ripgrep`, algunos pasos usan fallback `find/grep` con menor precisión.
- En corridas sin script `lint`, ESLint puede quedar `SKIPPED`.
- Esta auditoría **no implica corrección automática**.

## Recomendación de priorización

1. Estabilizar tests rotos (backend y frontend).
2. Atender seguridad/dependencias (Bandit HIGH/MEDIUM + npm audit).
3. Reducir errores de tipado (`mypy` / contratos TS).
4. Normalizar tooling faltante/entorno de auditoría.
5. Corregir violaciones de arquitectura y acoplamiento entre capas.
6. Ejecutar refactors de mantenibilidad (code smells, complejidad, duplicación/código muerto).

## Estado del Quality Gate

- Resultado: FAIL (según última consolidación automática disponible).
- Última ejecución: 2026-04-27T13:38:29+00:00.
- Modo: no bloqueante (Fase 5).
- Fuente: `audit/audit-status.json` evaluado por `scripts/audit/enforce_quality_gate.py`.

<!-- AUTO-AUDIT-SUMMARY:START -->
## Consolidación automática reproducible

- Generado: 2026-04-27T13:48:35+00:00
- Fuente automática: `audit/audit-summary.md`
- Estado machine-readable: `audit/audit-status.json`

- Estado general: FINDINGS
- Severidad máxima: critical
<!-- AUTO-AUDIT-SUMMARY:END -->
