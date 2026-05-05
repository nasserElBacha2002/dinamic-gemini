# Fase F1.0 — Baseline actual de Vitest frontend

## Estado

**F1.0 CERRADA CON OBSERVACIONES**

## Resumen ejecutivo

- Comando utilizado: `cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend" && npm run test`
- Estado general: señal de Vitest **reconfirmada** (fallos masivos vigentes).
- Test files fallidos: **19**
- Tests fallidos: **86**
- Tests pasados: **340**
- Tests skipped/todo: **0 / no reportado**
- Diferencia contra F0: **sin diferencia numérica** (se mantiene 86 failed en 19 archivos).
- Riesgo principal: regresión visible en flujos operativos UI (detalle de inventario, execution log, métricas, compare).
- Recomendación para F1.1: iniciar por `ExecutionLogPanel.test.tsx` (alto impacto operativo y volumen manejable: 6 fallos).

## Fuentes revisadas

- `audit/raw/frontend-vitest.txt`
- `audit/audit-summary.md`
- `audit/audit-status.json`
- `audit/frontend-f0-normalization.md`
- `frontend/package.json`
- Salidas de ejecución F1.0 (corrida completa + corridas críticas individuales)

## Resultado de corrida completa

```bash
cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend"
npm run test
```

Resultado resumido:

```txt
Test Files  19 failed | 49 passed (68)
Tests       86 failed | 340 passed (426)
Duration    15.16s
```

Notas:

- El script real en `frontend/package.json` es `test: "vitest run"`.
- Se observó warning de entorno npm (`Unknown env config "devdir"`), sin bloquear la ejecución.

## Tests críticos ejecutados individualmente

Comandos ejecutados:

```bash
cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend"
npm run test -- tests/ExecutionLogPanel.test.tsx
npm run test -- tests/CompareRunsPage.test.tsx
npm run test -- tests/MetricsPage.test.tsx
npm run test -- tests/InventoryDetailPage.test.tsx
```

| Test file | Estado | Tests fallidos | Causa probable | Alcance |
|---|---:|---:|---|---|
| `frontend/tests/ExecutionLogPanel.test.tsx` | FAIL | 6 (de 8) | `SELECTOR_ACCESIBLE_ROTO` | CRÍTICO_F1 |
| `frontend/tests/CompareRunsPage.test.tsx` | FAIL | 6 (de 9) | `COPY_DESACTUALIZADO` + `SELECTOR_ACCESIBLE_ROTO` | CRÍTICO_F1 |
| `frontend/tests/MetricsPage.test.tsx` | FAIL | 7 (de 13) | `COPY_DESACTUALIZADO` | CRÍTICO_F1 |
| `frontend/tests/InventoryDetailPage.test.tsx` | FAIL | 17 (de 21) | `SELECTOR_ACCESIBLE_ROTO` + `COPY_DESACTUALIZADO` | CRÍTICO_F1 |

## Lista de archivos fallidos detectados

| Archivo | Tests fallidos | Causa probable | Alcance sugerido |
|---|---:|---|---|
| `frontend/tests/InventoryDetailPage.test.tsx` | 17 | `SELECTOR_ACCESIBLE_ROTO` | CRÍTICO_F1 |
| `frontend/tests/CreateInventoryDialog.visualReferences.test.tsx` | 9 | `PENDIENTE_DE_REVISIÓN` | CANDIDATO_F1_5 |
| `frontend/tests/QuickReviewDrawer.test.tsx` | 8 | `PENDIENTE_DE_REVISIÓN` | CANDIDATO_F1_5 |
| `frontend/tests/MetricsPage.test.tsx` | 7 | `COPY_DESACTUALIZADO` | CRÍTICO_F1 |
| `frontend/tests/ExecutionLogPanel.test.tsx` | 6 | `SELECTOR_ACCESIBLE_ROTO` | CRÍTICO_F1 |
| `frontend/tests/CompareRunsPage.test.tsx` | 6 | `COPY_DESACTUALIZADO` / `SELECTOR_ACCESIBLE_ROTO` | CRÍTICO_F1 |
| `frontend/tests/auth/LoginPage.test.tsx` | 5 | `SELECTOR_ACCESIBLE_ROTO` | CANDIDATO_F1_5 |
| `frontend/tests/ReferenceImagesDrawer.test.tsx` | 5 | `PENDIENTE_DE_REVISIÓN` | CANDIDATO_F1_5 |
| `frontend/tests/api/evidenceImageLoad.test.tsx` | 4 | `MOCK_DESACTUALIZADO` (probable) | CANDIDATO_F1_5 |
| `frontend/tests/ReviewQueuePage.test.tsx` | 3 | `SELECTOR_ACCESIBLE_ROTO` (probable) | CANDIDATO_F1_5 |
| `frontend/tests/CreateAisleDialog.test.tsx` | 3 | `PENDIENTE_DE_REVISIÓN` | CANDIDATO_F1_5 |
| `frontend/tests/AislePositionsPage.test.tsx` | 3 | `SELECTOR_ACCESIBLE_ROTO` (probable) | CANDIDATO_F1_5 |
| `frontend/tests/ingestionSessionsR2Corrections.test.tsx` | 2 | `CAMBIO_REAL_DE_COMPORTAMIENTO` (probable) | FUERA_DE_ALCANCE_F1 |
| `frontend/tests/ResultReviewActions.test.tsx` | 2 | `PENDIENTE_DE_REVISIÓN` | CANDIDATO_F1_5 |
| `frontend/tests/AdminAiConfigPage.test.tsx` | 2 | `COPY_DESACTUALIZADO` | FUERA_DE_ALCANCE_F1 |
| `frontend/tests/RequireUsernameAdmin.test.tsx` | 1 | `COPY_DESACTUALIZADO` | CANDIDATO_F1_5 |
| `frontend/tests/PromoteOperationalDialog.test.tsx` | 1 | `COPY_DESACTUALIZADO` | FUERA_DE_ALCANCE_F1 |
| `frontend/tests/CompareRunsDialog.test.tsx` | 1 | `COPY_DESACTUALIZADO` | FUERA_DE_ALCANCE_F1 |
| `frontend/tests/AppShellAdminNav.test.tsx` | 1 | `COPY_DESACTUALIZADO` | FUERA_DE_ALCANCE_F1 |

## Clasificación por causa probable

| Causa probable | Cantidad aproximada | Ejemplos |
|---|---:|---|
| COPY_DESACTUALIZADO | 24 | `MetricsPage`, `CompareRunsPage`, `CompareRunsDialog`, `PromoteOperationalDialog` |
| SELECTOR_ACCESIBLE_ROTO | 35 | `ExecutionLogPanel` (`label Job`), `InventoryDetailPage` (`button/actions`), `LoginPage` (`label/text`) |
| MOCK_DESACTUALIZADO | 4 | `api/evidenceImageLoad.test.tsx` (errores por respuestas esperadas) |
| ASYNC_RENDER_INCOMPLETO | 6 | casos con `Unable to find...` en pantallas con carga dinámica (preliminar) |
| CAMBIO_REAL_DE_COMPORTAMIENTO | 2 | `ingestionSessionsR2Corrections.test.tsx` (semántica de cierre/aisle) |
| BUG_PRODUCTIVO | 0 | sin evidencia concluyente en F1.0 |
| CONFIG_TEST_ENV | 0 | sin evidencia concluyente en F1.0 |
| DEPENDIENTE_DE_F2_ESLINT | 0 | no bloquea ejecución Vitest |
| DEPENDIENTE_DE_F9_DEPENDENCIAS | 0 | no hay error de runtime atribuible a CVEs en esta corrida |
| PENDIENTE_DE_REVISIÓN | 15 | `QuickReviewDrawer`, `ReferenceImagesDrawer`, `CreateAisleDialog`, `ResultReviewActions` |

## Separación de alcance

### CRÍTICO_F1

- `frontend/tests/ExecutionLogPanel.test.tsx`
- `frontend/tests/CompareRunsPage.test.tsx`
- `frontend/tests/MetricsPage.test.tsx`
- `frontend/tests/InventoryDetailPage.test.tsx`

### CANDIDATO_F1_5

- `frontend/tests/auth/LoginPage.test.tsx`
- `frontend/tests/ReviewQueuePage.test.tsx`
- `frontend/tests/QuickReviewDrawer.test.tsx`
- `frontend/tests/api/evidenceImageLoad.test.tsx`
- `frontend/tests/ReferenceImagesDrawer.test.tsx`
- `frontend/tests/AislePositionsPage.test.tsx`
- `frontend/tests/CreateAisleDialog.test.tsx`
- `frontend/tests/ResultReviewActions.test.tsx`
- `frontend/tests/RequireUsernameAdmin.test.tsx`

### FUERA_DE_ALCANCE_F1

- `frontend/tests/AdminAiConfigPage.test.tsx`
- `frontend/tests/CompareRunsDialog.test.tsx`
- `frontend/tests/PromoteOperationalDialog.test.tsx`
- `frontend/tests/AppShellAdminNav.test.tsx`
- `frontend/tests/ingestionSessionsR2Corrections.test.tsx` (dejar para subfase posterior o validación funcional específica)

## Diferencias contra F0

- F0 reportaba: **86 tests fallidos en 19 archivos**.
- Estado actual F1.0: **86 tests fallidos en 19 archivos**.
- Diferencias: **sin cambios cuantitativos**.
- Posibles causas: deuda aún no atacada (F1 todavía no iniciada), alto acoplamiento entre copy/selección accesible/expectativas de tests.

## Recomendación

Avanzar a F1.1 comenzando por `ExecutionLogPanel.test.tsx`:

1. Alto impacto operativo.
2. Patrón de falla homogéneo (`Unable to find label/text`) y acotado.
3. Permite establecer estrategia reusable para `CompareRunsPage` y parte de `InventoryDetailPage`.

Orden sugerido de remediación:

1. `ExecutionLogPanel.test.tsx` (F1.1)
2. `CompareRunsPage.test.tsx` (F1.2)
3. `MetricsPage.test.tsx` (F1.3)
4. `InventoryDetailPage.test.tsx` (F1.4)

## Exclusiones explícitas

En F1.0 no se corrigió código productivo, tests, mocks, dependencias, ESLint ni arquitectura.

## Criterio de cierre

F1.0 se considera cerrada porque:

1. Se identificó el comando real de Vitest (`npm run test` en `frontend`).
2. Se ejecutó corrida completa y quedó documentada.
3. Se ejecutaron los 4 tests críticos de F1 individualmente.
4. Se clasificaron fallos por causa probable de forma preliminar.
5. Se separó alcance entre `CRÍTICO_F1`, `CANDIDATO_F1_5`, `FUERA_DE_ALCANCE_F1`.
6. No se modificó código productivo ni tests.
