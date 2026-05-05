# Fase F1.5 — Tests críticos candidatos restantes

## Estado

**F1.5 CERRADA**

## Resumen ejecutivo

- Baseline inicial F1.5: **50 failed / 15 failed files**.
- Resultado final F1.5: **16 failed / 6 failed files**.
- Tests fallidos al inicio: **50**.
- Tests fallidos al cierre: **16**.
- Test files fallidos al inicio: **15**.
- Test files fallidos al cierre: **6**.
- Archivos estabilizados: **9** (todos los candidatos de F1.5).
- Archivos derivados: **6** (fuera de alcance F1.5).
- Código productivo modificado: **No**.

## Baseline F1.5

```bash
cd frontend
npm run test
```

Resultado:

```txt
Test Files  15 failed | 53 passed (68)
Tests       50 failed | 376 passed (426)
```

## Archivos trabajados

| Archivo | Estado inicial | Estado final | Clasificación | Acción |
|---|---:|---:|---|---|
| `frontend/tests/auth/LoginPage.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Alineado a labels/copy actuales (`Login title`, botón `Login`), selector robusto para password input |
| `frontend/tests/ReviewQueuePage.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Alineación a nombres/labels reales (`review aria`, validaciones de confianza actuales) |
| `frontend/tests/QuickReviewDrawer.test.tsx` | FAIL | PASS | ENTRA_F1_5_LIMITADO | Ajuste de textos de snackbar/error y labels del confirm dialog al runtime actual |
| `frontend/tests/api/evidenceImageLoad.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Mensajes de error actualizados a i18n vigente (`source unavailable`, `forbidden`, `network`, `preview unavailable`) |
| `frontend/tests/ReferenceImagesDrawer.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Alineación de empty/management/delete title y errores de preview al runtime actual |
| `frontend/tests/AislePositionsPage.test.tsx` | FAIL | PASS | ENTRA_F1_5_LIMITADO | Selectores de review/promote y copy de merge summary actualizados; aserciones desacopladas de copy legado |
| `frontend/tests/CreateAisleDialog.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Labels/CTA/mensajes de validación y éxito actualizados a traducciones actuales |
| `frontend/tests/ResultReviewActions.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Placeholder qty y mensaje readOnly alineados a runtime actual |
| `frontend/tests/RequireUsernameAdmin.test.tsx` | FAIL | PASS | ENTRA_F1_5 | Mensaje unauthorized alineado a copy actual |

## Cambios realizados

| Archivo | Tipo | Motivo |
|---|---|---|
| `frontend/tests/auth/LoginPage.test.tsx` | Test | Selectores accesibles robustos y copy actualizado |
| `frontend/tests/RequireUsernameAdmin.test.tsx` | Test | Copy actualizado |
| `frontend/tests/ReviewQueuePage.test.tsx` | Test | Copy + selector accesible actualizado |
| `frontend/tests/QuickReviewDrawer.test.tsx` | Test | Copy actualizado en snackbar/errores/dialog |
| `frontend/tests/ResultReviewActions.test.tsx` | Test | Placeholder y mensaje readOnly actualizados |
| `frontend/tests/api/evidenceImageLoad.test.tsx` | Test | Mensajes de error alineados a hook/i18n |
| `frontend/tests/ReferenceImagesDrawer.test.tsx` | Test | Copy de drawer/dialog actualizado |
| `frontend/tests/AislePositionsPage.test.tsx` | Test | Selectores y textos de acciones operativas actualizados |
| `frontend/tests/CreateAisleDialog.test.tsx` | Test | Labels/validaciones/éxito actualizados |
| `audit/frontend-f1-5-candidate-tests.md` | Documentación | Cierre F1.5 |

## Fallos corregidos por causa

| Causa | Archivos | Corrección típica |
|---|---|---|
| COPY_DESACTUALIZADO | LoginPage, RequireUsernameAdmin, ReviewQueuePage, QuickReviewDrawer, ReferenceImagesDrawer, AislePositionsPage, CreateAisleDialog, ResultReviewActions | Expectations a copy runtime (placeholder/i18n vigente) |
| I18N_PLACEHOLDER_ACTUAL | 9/9 archivos candidatos | Assertions actualizadas a keys visibles actuales |
| SELECTOR_ACCESIBLE_ROTO | LoginPage, ReviewQueuePage, AislePositionsPage, CreateAisleDialog | `getByRole/getByLabelText` sobre nombres accesibles reales |
| MOCK_DESACTUALIZADO | QuickReviewDrawer, AislePositionsPage | Expectativas de callbacks/mensajes ajustadas a flujos actuales |
| ASYNC_RENDER_INCOMPLETO | QuickReviewDrawer, ReferenceImagesDrawer | Uso de `waitFor`/`findBy*` con mensajes actuales |
| NAVIGATION_EXPECTATION_OUTDATED | AislePositionsPage | Labels de acciones y CTA de promote/merge alineados a UI actual |

## Archivos derivados fuera de F1.5

| Archivo | Motivo de derivación | Fase sugerida |
|---|---|---|
| `frontend/tests/AdminAiConfigPage.test.tsx` | Fuera de alcance F1.5 según consigna (admin AI config) | F1.5b o F1.6 |
| `frontend/tests/CompareRunsDialog.test.tsx` | Fuera de alcance en esta subfase | F1.5b o F1.6 |
| `frontend/tests/PromoteOperationalDialog.test.tsx` | Fuera de alcance en esta subfase | F1.5b o F1.6 |
| `frontend/tests/AppShellAdminNav.test.tsx` | Fuera de alcance en esta subfase | F1.5b o F1.6 |
| `frontend/tests/ingestionSessionsR2Corrections.test.tsx` | Fuera de alcance en esta subfase | F1.5b o F1.6 |
| `frontend/tests/CreateInventoryDialog.visualReferences.test.tsx` | Fuera de alcance por volumen/complejidad (9 fallos) | F1.5b dedicada |

## Validación ejecutada

### Tests por batch

```bash
cd frontend
npm run test -- tests/auth/LoginPage.test.tsx tests/RequireUsernameAdmin.test.tsx
npm run test -- tests/ReviewQueuePage.test.tsx tests/QuickReviewDrawer.test.tsx tests/ResultReviewActions.test.tsx
npm run test -- tests/api/evidenceImageLoad.test.tsx tests/ReferenceImagesDrawer.test.tsx tests/AislePositionsPage.test.tsx tests/CreateAisleDialog.test.tsx
```

Resultado:

```txt
Batch A: 8 passed
Batch B: 26 passed
Batch C+D: 45 passed
```

### Suite completa final

```bash
cd frontend
npm run test
```

Resultado:

```txt
Test Files  6 failed | 62 passed (68)
Tests       16 failed | 410 passed (426)
```

## Observaciones

- Patrón dominante: desalineación test-vs-runtime (copy/labels/i18n placeholders), no bug productivo.
- No se necesitaron cambios en componentes/productivo para cerrar candidatos F1.5.
- Persisten warnings no bloqueantes de React Router future flags y un warning de DOM nesting en preview dialog (no abordado por alcance F1.5).
- Queda pendiente una pasada focalizada para los 6 archivos restantes (fuera de alcance definido en esta subfase).

## Criterio de cierre

F1.5 se considera cerrada porque:

1. Se reconfirmó baseline post F1.4.
2. Se evaluaron y ejecutaron los 9 candidatos F1.5.
3. Se estabilizaron todos los candidatos corregibles sin refactor.
4. Se documentaron explícitamente los derivados fuera de alcance.
5. No se mezcló con ESLint, arquitectura, dependencias ni complejidad.
6. La suite final mejoró de forma significativa (**50 -> 16 failed**, **15 -> 6 failed files**).
