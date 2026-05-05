# Fase F0 — Normalización de auditoría frontend

## Resumen ejecutivo

- Estado general: **F0 CERRADA CON OBSERVACIONES** (normalización documental completada con diferencias detectadas entre consolidados).
- Hallazgos confirmados: **5** (ESLint, Vitest, Typecheck, npm audit, señales concretas de complejidad).
- Hallazgos heurísticos: **4** (useEffect audit, dead code, reusable components, SOLID/React).
- Hallazgos pendientes de revisión: **2** (import boundaries y error handling por falta de validación semántica/arquitectónica).
- Falsos positivos: **1 bloque principal** (dead code `ts-prune` con alta proporción de `used in module`; además varios heurísticos no son evidencia de defecto por sí solos).
- Riesgo principal: inestabilidad funcional visible por **86 tests frontend fallidos** y deuda de lint en hooks/estado.
- Recomendación para F1: atacar primero estabilización de tests críticos por flujo de negocio (pantallas operativas y auth), sin mezclar con refactor de arquitectura.

## Fuentes revisadas

### Consolidados

- `audit/audit-report.md`
- `audit/audit-backlog.md`
- `audit/audit-summary.md`
- `audit/audit-status.json`

### Raw frontend

- `audit/raw/frontend-eslint.txt`
- `audit/raw/frontend-vitest.txt`
- `audit/raw/frontend-typecheck.txt`
- `audit/raw/frontend-npm-audit.json`
- `audit/raw/frontend-useeffects-audit.md`
- `audit/raw/frontend-complexity.txt`
- `audit/raw/frontend-import-boundaries.txt`
- `audit/raw/frontend-dead-code.txt`
- `audit/raw/frontend-error-handling-audit.md`
- `audit/raw/frontend-reusable-components-audit.md`
- `audit/raw/frontend-solid-react-audit.md`
- `audit/raw/frontend-code-smells.txt`
- `audit/raw/frontend-duplication.txt`

## Matriz de clasificación

| Área | Estado | Evidencia | Archivos afectados | Fase sugerida |
|---|---|---|---|---|
| ESLint | CONFIRMADO | `frontend-eslint.txt`: 66 problemas (40 errors, 26 warnings), con regla explícita `react-hooks/set-state-in-effect` y rutas concretas | `frontend/src/**`, `frontend/tests/**` | F2 |
| Vitest | CONFIRMADO | `frontend-vitest.txt`: 19 archivos fallidos, 86 tests fallidos, 340 passed | `frontend/tests/**` | F1 |
| Typecheck | CONFIRMADO | `frontend-typecheck.txt`: `tsc --noEmit` sin errores (estado OK confirmado) | `frontend/src/**` | F2 (gate preventivo, no corrección urgente) |
| npm audit | CONFIRMADO | `frontend-npm-audit.json`: 7 moderadas (vite/vitest/esbuild/postcss/yaml), 0 high/critical | `frontend/package-lock.json` (sin cambios en F0) | F9 |
| useEffect | HEURÍSTICO | `frontend-useeffects-audit.md`: 46 usos, 20 archivos, varios patrones en 0; reporte explícitamente heurístico | `frontend/src/**` | F3 |
| Complexity | CONFIRMADO | `frontend-complexity.txt`: 183 archivos escaneados, 19 >300 líneas, 4 >1000 líneas; evidencia objetiva de tamaño | `frontend/src/features/analytics/MetricsPage.tsx`, `frontend/src/api/client.ts`, otros | F5 |
| Import boundaries | PENDIENTE_DE_REVISIÓN | `frontend-import-boundaries.txt`: 8 señales `R1 components->api/fetch`, con tooling formal no instalado (`madge`, `dependency-cruiser`) | `frontend/src/components/**` | F4 |
| Dead code | HEURÍSTICO | `frontend-dead-code.txt`: 470/471 señales `ts-prune`; múltiples entradas marcadas `used in module` | `frontend/src/**` | F8 |
| Error handling | PENDIENTE_DE_REVISIÓN | `frontend-error-handling-audit.md`: 100 archivos, 59 try, 25 catch, conteos por patrón textual | `frontend/src/**`, `frontend/tests/**` | F6 |
| Reusable components | HEURÍSTICO | `frontend-reusable-components-audit.md`: 0 archivos candidatos, solo conteos de referencias (Button/Card/Dialog/etc.) | `frontend/src/**` | F7 |
| SOLID React | HEURÍSTICO | `frontend-solid-react-audit.md`: señales agregadas (18/16/23/471/77) con limitación explícita de falsos positivos | `frontend/src/**` | F10 |

## Diferencias encontradas entre reportes

### Coincidencias principales (frontend)

- ESLint: coincide en **66 problemas** (`audit-summary`, `audit-status`, `raw`).
- Vitest: coincide en **86 fallos** y **19 archivos fallidos**.
- Typecheck: coincide en **0 errores TS**.
- npm audit: coincide en **7 moderadas**.
- useEffect / error handling / reusable components: métricas agregadas alineadas con raw.

### Diferencias y observaciones

- `audit/audit-report.md` contiene parte de frontend alineada, pero mezcla contexto histórico y estado global no homogéneo con el consolidado más reciente.
- `audit/audit-report.md` menciona en arquitectura frontend **23 señales de imports sospechosos**, mientras `audit/audit-summary.md` y `audit/audit-status.json` reportan **8 señales** en `frontend-import-boundaries.txt` (estado actual raw).
- `audit/audit-backlog.md` es correcto como backlog operativo, pero no distingue de forma explícita en todas las entradas frontend entre evidencia confirmada vs heurística; F0 deja esa separación trazable.
- `audit/audit-summary.md` y `audit/audit-status.json` son los consolidados más consistentes con evidencia raw actual para frontend.

## Priorización recomendada (post-F0)

1. **F1 — Tests críticos:** estabilizar fallos Vitest por impacto en flujo de usuario (operaciones principales + auth).
2. **F2 — ESLint y hooks:** resolver errores reales de lint (prioridad `react-hooks/set-state-in-effect`) y definir política de warnings.
3. **F9 — Dependencias frontend:** plan de upgrade controlado de Vite/Vitest/toolchain con validación de compatibilidad.
4. **F3 — useEffect conceptual:** revisar efectos con debt conceptual una vez estabilizados tests/lint.
5. **F4 — Separación components -> api/fetch:** validar intención arquitectónica y extraer capa intermedia donde corresponda.
6. **F5 — Complejidad:** dividir archivos grandes priorizando `MetricsPage` y `api/client`.
7. **F6 — Manejo de errores:** estandarizar patrón UX de errores por capa.
8. **F7 — Componentes reutilizables:** inventario y convergencia de patrones UI.
9. **F8 — Código muerto:** clasificación manual de `ts-prune` antes de eliminar.
10. **F10 — Revisión SOLID/React final:** cierre de arquitectura luego de refactors previos.

## Exclusiones explícitas

En F0 **no** se realizó:

- Corrección de código productivo.
- Corrección de tests.
- Corrección de ESLint.
- Actualización de dependencias.
- Refactors de componentes o lógica.
- Activación de CI/CD, pipelines, hooks pre-push o quality gates automáticos.

## Criterio de cierre

La fase se considera cerrada porque:

1. Se revisaron y contrastaron los archivos de auditoría frontend (consolidados y raw).
2. Se clasificaron los hallazgos principales por estado de evidencia.
3. Se separaron hallazgos confirmados de heurísticos/pendientes.
4. Se definió qué corresponde atacar en F1 y F2 sin mezclar fases.
5. No se modificó código productivo, tests ni dependencias.
