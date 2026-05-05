# Fase F2.2 — Correccion de react-hooks/exhaustive-deps

## Estado

F2.2 CERRADA CON OBSERVACIONES

## Resumen ejecutivo

- Baseline inicial `react-hooks/exhaustive-deps`: 17
- Resultado final `react-hooks/exhaustive-deps`: 0
- Warnings eliminados: 17
- Remanentes derivados a F3: 0 (para esta regla)
- Archivos productivos modificados: 7
- Tests modificados: 0
- Resultado ESLint: `react-hooks/exhaustive-deps: 0`, `react-hooks/set-state-in-effect: 0`, pero quedan 18 problemas de otras reglas (11 errores, 7 warnings)
- Resultado Vitest: tests puntuales objetivo en verde; suite completa se mantiene en `31 failed / 9 failed files` (no mejora respecto a cierre previo de F2.1 y peor que cierre F1)

## Archivos modificados

| Archivo | Tipo | Casos corregidos | Estrategia |
|---|---|---:|---|
| `frontend/src/components/ExecutionLogPanel.tsx` | Productivo | 2 | `OBJETO_ARRAY_INLINE` con `useMemo` para estabilizar `allEvents` |
| `frontend/src/pages/ReviewQueuePage.tsx` | Productivo | 3 | `OBJETO_ARRAY_INLINE` + deps de callback/query mas precisas |
| `frontend/src/pages/InventoryDetail.tsx` | Productivo | 2 | `OBJETO_ARRAY_INLINE` con `useMemo` para `aisles` |
| `frontend/src/pages/AislePositionsPage.tsx` | Productivo | 7 | `OBJETO_ARRAY_INLINE` + `EFECTO_CON_GUARD` + dependencia faltante en callback |
| `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx` | Productivo | 1 | `FUNCION_RECREADA` (agregar `onClose` a deps) |
| `frontend/src/pages/analytics/CompareRunsPage.tsx` | Productivo | 1 | `OBJETO_ARRAY_INLINE` con `useMemo` para `jobs` |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | Productivo | 1 | `OBJETO_ARRAY_INLINE` con `useMemo` para `jobs` |
| `audit/frontend-f2-2-exhaustive-deps.md` | Documentacion | - | Cierre de fase |

## Casos corregidos por categoria

| Categoria | Cantidad | Archivos | Estrategia |
|---|---:|---|---|
| `OBJETO_ARRAY_INLINE` | 13 | ExecutionLogPanel, ReviewQueuePage, InventoryDetail, AislePositionsPage, CompareRunsPage, CompareManyRunsPage | memoizacion (`useMemo`) de expresiones `?? []` y valores derivados |
| `FUNCION_RECREADA` | 2 | QuickReviewDrawer, AislePositionsPage | agregar dependencia real al callback |
| `EFECTO_CON_GUARD` | 2 | AislePositionsPage, ReviewQueuePage | dependencias completas con guards existentes |
| `DERIVAR_F3` | 0 | - | - |

## Validacion ejecutada

### ESLint

```bash
cd frontend
npx eslint . -f json
```

Resultado relevante:

```txt
react-hooks/exhaustive-deps: 0
react-hooks/set-state-in-effect: 0
```

Ejecucion completa de `npm run lint`:

```txt
18 problems (11 errors, 7 warnings)
```

Sin hallazgos de `react-hooks/exhaustive-deps`.

### Tests puntuales

```bash
cd frontend
npm run test -- tests/ExecutionLogPanel.test.tsx tests/MetricsPage.test.tsx tests/InventoryDetailPage.test.tsx tests/QuickReviewDrawer.test.tsx tests/ReviewQueuePage.test.tsx tests/AislePositionsPage.test.tsx tests/CompareRunsPage.test.tsx tests/CreateAisleDialog.test.tsx tests/ResultReviewActions.test.tsx tests/api/evidenceImageLoad.test.tsx
```

Resultado:

```txt
Test Files  10 passed (10)
Tests      112 passed (112)
```

### Suite completa

```bash
cd frontend
npm run test
```

Resultado:

```txt
Test Files  9 failed | 59 passed (68)
Tests      31 failed | 395 passed (426)
```

## Pendientes derivados

| Archivo | Motivo | Fase sugerida |
|---|---|---|
| Varias ubicaciones (no `exhaustive-deps`) | Limpieza mecanica de reglas ESLint restantes (`no-unused-vars`, `no-useless-assignment`, `prefer-as-const`, `react-refresh/only-export-components`, etc.) | F2.3/F2.4/F2.5 |
| `tests/QuickReviewDrawer.anchorSync.test.tsx`, `tests/auth/LoginPage.test.tsx`, `tests/ingestionSessionsR2Corrections.test.tsx` y otros ya fallando | Regresiones/expectativas previas fuera del alcance de F2.2 | F1.5/F2.1 estabilizacion adicional o F3 segun caso |

## Observaciones

- No se agregaron `eslint-disable` para resolver `exhaustive-deps`.
- No se uso `queueMicrotask`.
- Cambios de F2.2 se limitaron a dependencias y estabilizacion de referencias.
- Vitest no empeora respecto al cierre previo de F2.1, pero sigue peor que el cierre F1.
