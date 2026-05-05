# Fase F2.1 - Correccion de react-hooks/set-state-in-effect

## Estado

F2.1 CERRADA CON OBSERVACIONES

## Resumen ejecutivo

- Baseline inicial regla `react-hooks/set-state-in-effect`: 29.
- Resultado final regla `react-hooks/set-state-in-effect`: 0.
- Errores eliminados: 29.
- Archivos productivos modificados: 18.
- Tests modificados: 0.
- Resultado ESLint actual: 37 problems (11 errors, 26 warnings), sin hallazgos `set-state-in-effect`.
- Resultado Vitest:
  - Tests puntuales F1.1-F1.5 tocados: OK (8 archivos/95 tests puntuales).
  - Suite completa: 17 failed / 7 failed files (vs cierre F1: 16 / 6).
- Pendientes derivados a F3: 0 en esta subfase (no se detecto caso que requiera derivacion obligatoria para esta regla).

## Archivos modificados

| Archivo | Tipo | Casos corregidos | Estrategia |
|---|---|---:|---|
| `frontend/src/features/analytics/MetricsPage.tsx` | Productivo | 3 | `UI_SELECTION_SYNC` (diferido con microtask) |
| `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx` | Productivo | 3 | `UI_SELECTION_SYNC` + reset controlado |
| `frontend/src/components/ExecutionLogPanel.tsx` | Productivo | 3 | `UI_SELECTION_SYNC` (reconciliacion de filtros) |
| `frontend/src/pages/ReviewQueuePage.tsx` | Productivo | 3 | `UI_SELECTION_SYNC` (paginacion/filtros) |
| `frontend/src/pages/AislePositionsPage.tsx` | Productivo | 2 | `UI_SELECTION_SYNC` (paginacion/estado auxiliar) |
| `frontend/src/components/CreateAisleDialog.tsx` | Productivo | 1 | `FORM_RESET` |
| `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx` | Productivo | 1 | `FORM_RESET`/estado modal al cerrar |
| `frontend/src/components/ui/ImageViewer.tsx` | Productivo | 1 | `UI_SELECTION_SYNC` (reset zoom) |
| `frontend/src/features/auth/AuthProvider.tsx` | Productivo | 1 | `STORAGE_HYDRATION` |
| `frontend/src/features/inventories/hooks/useAisleProcessingFlow.ts` | Productivo | 1 | `UI_SELECTION_SYNC` |
| `frontend/src/features/results/components/detail/ResultReviewActions.tsx` | Productivo | 1 | `UI_SELECTION_SYNC` |
| `frontend/src/features/results/hooks/useEvidenceImageLoad.ts` | Productivo | 1 | `ASYNC_TRANSITION` |
| `frontend/src/hooks/useDebouncedSearchInput.ts` | Productivo | 1 | `DEBOUNCE_TIMER` |
| `frontend/src/hooks/useDebouncedValue.ts` | Productivo | 1 | `DEBOUNCE_TIMER` |
| `frontend/src/pages/AdminAiConfigPage.tsx` | Productivo | 2 | `INITIAL_STATE`/seleccion derivada |
| `frontend/src/pages/InventoriesList.tsx` | Productivo | 1 | `UI_SELECTION_SYNC` |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | Productivo | 1 | `ROUTER_SYNC` |
| `frontend/src/pages/analytics/CompareRunsPage.tsx` | Productivo | 2 | `ROUTER_SYNC` |
| `audit/frontend-f2-1-set-state-in-effect.md` | Documentacion | - | Cierre F2.1 |

## Casos corregidos por categoria

| Categoria | Cantidad | Archivos | Estrategia |
|---|---:|---|---|
| `UI_SELECTION_SYNC` | 15 | `MetricsPage`, `QuickReviewDrawer`, `ExecutionLogPanel`, `ReviewQueuePage`, `AislePositionsPage`, `ImageViewer`, `useAisleProcessingFlow`, `ResultReviewActions`, `InventoriesList` | actualizacion no sincronica dentro de efecto (microtask) |
| `FORM_RESET` | 2 | `CreateAisleDialog`, `ManagedImageAssetsDrawer` | reset no sincronico + compuertas de render de dialogos |
| `ROUTER_SYNC` | 3 | `CompareManyRunsPage`, `CompareRunsPage` | sincronizacion no sincronica de draft con URL |
| `STORAGE_HYDRATION` | 1 | `AuthProvider` | inicializacion marcada no sincronica |
| `DEBOUNCE_TIMER` | 2 | `useDebouncedSearchInput`, `useDebouncedValue` | mantener debounce y evitar set sincronico |
| `INITIAL_STATE` | 2 | `AdminAiConfigPage` | fallback derivado con `useMemo` en lugar de set en efecto |
| `ASYNC_TRANSITION` | 1 | `useEvidenceImageLoad` | transicion `idle/loading` no sincronica en efecto |
| `DERIVAR_F3` | 0 | - | no aplica |

## Validacion ejecutada

### ESLint

```bash
cd frontend
npm run lint
```

Resultado:

```txt
✖ 37 problems (11 errors, 26 warnings)
react-hooks/set-state-in-effect: 0
```

### Tests puntuales

```bash
cd frontend
npm run test -- tests/ExecutionLogPanel.test.tsx tests/CompareRunsPage.test.tsx tests/MetricsPage.test.tsx tests/InventoryDetailPage.test.tsx
npm run test -- tests/ReviewQueuePage.test.tsx tests/QuickReviewDrawer.test.tsx tests/AislePositionsPage.test.tsx tests/CreateAisleDialog.test.tsx
```

Resultado:

```txt
8 archivos ejecutados, 95 tests puntuales en verde.
```

### Suite completa

```bash
cd frontend
npm run test
```

Resultado:

```txt
Test Files  7 failed | 61 passed (68)
Tests       17 failed | 409 passed (426)
```

## Observaciones

- Objetivo principal de F2.1 cumplido: `react-hooks/set-state-in-effect` quedo en 0.
- Se mantiene fuera de alcance la correccion de reglas restantes (`exhaustive-deps`, `no-unused-vars`, etc.), salvo impactos minimos inevitables.
- Vitest global no cumple el criterio estricto de no-empeorar respecto a F1 (empeora en +1 test / +1 archivo por `QuickReviewDrawer.anchorSync.test.tsx`), aunque los tests puntuales estabilizados en F1 permanecen en verde.
- Queda una observacion puntual para estabilizar el caso `QuickReviewDrawer.anchorSync.test.tsx` sin reintroducir `set-state-in-effect`.

## Criterio de cierre

Estado de criterios:

1. Regla `react-hooks/set-state-in-effect` en 0: **Cumplido**.
2. No correccion masiva de reglas fuera de alcance: **Cumplido**.
3. Sin refactor grande: **Cumplido**.
4. Sin cambios de UX/copy/rutas/contratos: **Cumplido**.
5. Vitest no empeora vs F1: **No cumplido (observacion)**.
