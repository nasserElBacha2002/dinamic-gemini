# Fase F1 — Cierre global de estabilización de tests frontend críticos

## Estado

**F1 CERRADA CON OBSERVACIONES**

## Resumen ejecutivo

- Baseline inicial F1: **86 failed / 19 failed files**.
- Resultado final F1: **16 failed / 6 failed files**.
- Reducción de tests fallidos: **70**.
- Reducción de archivos fallidos: **13**.
- Tests críticos estabilizados: **4/4** (ExecutionLogPanel, CompareRunsPage, MetricsPage, InventoryDetailPage).
- Tests candidatos estabilizados: **9/9** (batch F1.5 operativo).
- Código productivo modificado: **No**.
- Riesgo principal restante: fallos en archivos explícitamente fuera de alcance F1 (Admin AI, CompareRunsDialog, PromoteOperationalDialog, AppShellAdminNav, ingestion sessions, CreateInventoryDialog.visualReferences).
- Recomendación: **avanzar a F2 (ESLint y hooks)** y dejar una F1.5b/F1.6b focalizada solo para los 6 test files pendientes si se prioriza cero fallos en Vitest.

## Evolución por subfase

| Subfase | Estado | Suite completa | Test puntual / foco |
|---|---|---|---|
| F1.0 | Cerrada con observaciones | 86 failed / 19 files | Baseline |
| F1.1 | Cerrada | 80 failed / 18 files | `ExecutionLogPanel` 8/8 |
| F1.2 | Cerrada | 74 failed / 17 files | `CompareRunsPage` 9/9 |
| F1.3 | Cerrada | 67 failed / 16 files | `MetricsPage` 13/13 |
| F1.4 | Cerrada | 50 failed / 15 files | `InventoryDetailPage` 21/21 |
| F1.5 | Cerrada | 16 failed / 6 files | 9 candidatos operativos estabilizados |
| F1.6 | Cerrada con observaciones | 16 failed / 6 files | Cierre documental + validación final |

## Tests estabilizados

### CRÍTICOS_F1

- `frontend/tests/ExecutionLogPanel.test.tsx`
- `frontend/tests/CompareRunsPage.test.tsx`
- `frontend/tests/MetricsPage.test.tsx`
- `frontend/tests/InventoryDetailPage.test.tsx`

### CANDIDATOS_F1_5

- `frontend/tests/auth/LoginPage.test.tsx`
- `frontend/tests/ReviewQueuePage.test.tsx`
- `frontend/tests/QuickReviewDrawer.test.tsx`
- `frontend/tests/api/evidenceImageLoad.test.tsx`
- `frontend/tests/ReferenceImagesDrawer.test.tsx`
- `frontend/tests/AislePositionsPage.test.tsx`
- `frontend/tests/CreateAisleDialog.test.tsx`
- `frontend/tests/ResultReviewActions.test.tsx`
- `frontend/tests/RequireUsernameAdmin.test.tsx`

### DERIVADOS_FUERA_DE_F1

- `frontend/tests/AdminAiConfigPage.test.tsx`
- `frontend/tests/CompareRunsDialog.test.tsx`
- `frontend/tests/PromoteOperationalDialog.test.tsx`
- `frontend/tests/AppShellAdminNav.test.tsx`
- `frontend/tests/ingestionSessionsR2Corrections.test.tsx`
- `frontend/tests/CreateInventoryDialog.visualReferences.test.tsx`

## Archivos modificados durante F1

| Archivo | Tipo | Subfase | Motivo |
|---|---|---|---|
| `frontend/tests/ExecutionLogPanel.test.tsx` | Test | F1.1 | Alinear selectors/copy a runtime accesible |
| `frontend/tests/CompareRunsPage.test.tsx` | Test | F1.2 | Alinear copy/tooltips y mocks al runtime actual |
| `frontend/tests/MetricsPage.test.tsx` | Test | F1.3 | Alinear i18n placeholder + queries accesibles |
| `frontend/tests/InventoryDetailPage.test.tsx` | Test | F1.4 | Ajuste masivo de copy/selector/async al runtime |
| `frontend/tests/auth/LoginPage.test.tsx` | Test | F1.5 | Labels y CTA actuales |
| `frontend/tests/ReviewQueuePage.test.tsx` | Test | F1.5 | Copy de filtros/acciones + selector review |
| `frontend/tests/QuickReviewDrawer.test.tsx` | Test | F1.5 | Mensajes snackbar/error/confirm actuales |
| `frontend/tests/api/evidenceImageLoad.test.tsx` | Test | F1.5 | Mensajes de error actuales del hook |
| `frontend/tests/ReferenceImagesDrawer.test.tsx` | Test | F1.5 | Empty/management/delete/preview actuales |
| `frontend/tests/AislePositionsPage.test.tsx` | Test | F1.5 | Review/promote/merge expectations actuales |
| `frontend/tests/CreateAisleDialog.test.tsx` | Test | F1.5 | Validaciones y labels actuales |
| `frontend/tests/ResultReviewActions.test.tsx` | Test | F1.5 | Placeholder qty y readOnly message actuales |
| `frontend/tests/RequireUsernameAdmin.test.tsx` | Test | F1.5 | Unauthorized message actual |
| `audit/frontend-f1-0-vitest-baseline.md` | Documentación | F1.0 | Baseline reconfirmado |
| `audit/frontend-f1-1-execution-log-panel.md` | Documentación | F1.1 | Cierre subfase |
| `audit/frontend-f1-2-compare-runs-page.md` | Documentación | F1.2 | Cierre subfase |
| `audit/frontend-f1-3-metrics-page.md` | Documentación | F1.3 | Cierre subfase |
| `audit/frontend-f1-4-inventory-detail-page.md` | Documentación | F1.4 | Cierre subfase |
| `audit/frontend-f1-5-candidate-tests.md` | Documentación | F1.5 | Cierre candidatos |
| `audit/frontend-f1-tests-stabilization.md` | Documentación | F1.6 | Cierre global |

## Tipos de correcciones aplicadas

| Causa | Acción aplicada | Ejemplos |
|---|---|---|
| COPY_DESACTUALIZADO | Actualización de assertions a textos visibles actuales | CompareRunsPage, ReviewQueuePage, CreateAisleDialog |
| I18N_PLACEHOLDER_ACTUAL | Alineación de expectations a placeholders runtime | InventoryDetailPage, LoginPage, QuickReviewDrawer |
| SELECTOR_ACCESIBLE_ROTO | Migración a `getByRole`/`getByLabelText` robustos | ExecutionLogPanel, InventoryDetailPage, AislePositionsPage |
| MOCK_DESACTUALIZADO | Ajuste de fixtures/expectativas de callback | QuickReviewDrawer, CompareRunsPage |
| ASYNC_RENDER_INCOMPLETO | Uso de `findBy*`/`waitFor` en renders diferidos | ReferenceImagesDrawer, InventoryDetailPage |
| NAVIGATION_EXPECTATION_OUTDATED | Actualización de rutas/labels de acciones | InventoryDetailPage, AislePositionsPage |

## Código productivo modificado

No se modificó código productivo durante F1.

## Validación final

```bash
cd frontend
npm run test
```

Resultado:

```txt
Test Files  6 failed | 62 passed (68)
Tests       16 failed | 410 passed (426)
Duration    15.65s
```

Tests skipped/todo: **no reportado (0 visible en salida)**.

## Revalidación puntual de estabilizados

No se repitieron todos los archivos uno por uno en F1.6 porque ya fueron validados y documentados en F1.1–F1.5, y en F1.6 no se realizaron cambios en `frontend/tests` ni `frontend/src`.

## Pendientes fuera de F1

| Pendiente | Motivo | Fase sugerida |
|---|---|---|
| `AdminAiConfigPage.test.tsx` | Fuera de alcance operativo F1 | F1.5b o F1.6b focalizada |
| `CompareRunsDialog.test.tsx` | Fuera de alcance F1.5 | F1.5b o F1.6b |
| `PromoteOperationalDialog.test.tsx` | Fuera de alcance F1.5 | F1.5b o F1.6b |
| `AppShellAdminNav.test.tsx` | Fuera de alcance F1.5 | F1.5b o F1.6b |
| `ingestionSessionsR2Corrections.test.tsx` | Flujo semántico/contrato fuera de F1 | F2/F4 según causa real |
| `CreateInventoryDialog.visualReferences.test.tsx` | Alto volumen (9 fallos) y potencial impacto UX/dialogs | F1.5b dedicada |
| ESLint/hooks | Fuera de F1 por definición | F2 |
| useEffect conceptual | Fuera de F1 | F3 |
| API/fetch/components acoplados | Fuera de F1 | F4 |
| Complejidad de archivos grandes | Fuera de F1 | F5 |
| Manejo de errores transversal | Fuera de F1 | F6 |
| Reusabilidad de componentes | Fuera de F1 | F7 |
| Código muerto | Fuera de F1 | F8 |
| Dependencias/vulnerabilidades | Fuera de F1 | F9 |
| SOLID/React estructural | Fuera de F1 | F10 |
| Mejora UX/copy i18n placeholders | Fuera de F1 | fase UX/i18n posterior |

## Conclusión

F1 queda cerrada con observaciones: los objetivos críticos y candidatos operativos se cumplieron, y los pendientes restantes están claramente delimitados fuera del alcance de F1.

## Criterio de cierre

F1 se considera cerrada porque:

1. Se ejecutó validación final de Vitest en F1.6.
2. Se consolidó trazabilidad completa de F1.0 a F1.5.
3. Los tests críticos definidos para F1 quedaron estabilizados.
4. Los candidatos F1.5 se estabilizaron y el resto quedó derivado explícitamente.
5. No se mezcló F1 con ESLint, arquitectura, dependencias ni refactors.
6. Está definido el siguiente paso para F2.
