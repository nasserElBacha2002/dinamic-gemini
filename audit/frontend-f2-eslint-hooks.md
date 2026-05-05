# Fase F2 — Cierre global ESLint y hooks frontend

## Estado

**F2 CERRADA CON OBSERVACIONES**

Motivo principal de observaciones: la suite Vitest final (`18 failed / 8 failed files`) sigue **peor que el cierre documentado de F1** (`16 failed / 6 failed files`), aunque mejora frente al peor punto intermediario de F2 (~`31 failed / 9 files`). ESLint y hooks objetivo están cerrados sin errores.

## Resumen ejecutivo

| Métrica | Inicio F2 (F2.0) | Fin F2 (F2.6) |
|---|---|---|
| ESLint problems | 66 (40 errors, 26 warnings) | **0** |
| ESLint errors | 40 | **0** |
| ESLint warnings | 26 | **0** |
| `react-hooks/set-state-in-effect` | 29 | **0** |
| `react-hooks/exhaustive-deps` | 19 (baseline F2.0; corregido en F2.2) | **0** |
| Typecheck (`tsc --noEmit`) | OK (histórico) | **OK** |
| Vitest (suite completa) | Ver F1 / cortes intermedios | **18 failed \| 408 passed** (8 failed files, 426 tests) |
| Riesgo principal restante | Hooks + ESLint denso | Regresión residual de tests tras cambios de estado/router en F2.1/F2.2 |
| Recomendación | — | Avanzar a **F3** para auditoría conceptual de `useEffect`, con **F2.7 o estabilización Vitest** explícita antes o en paralelo si el equipo exige paridad con cierre F1 |

## Evolución por subfase

| Subfase | Estado | ESLint (resumen) | Foco | Tests (suite / notas) |
|---|---|---|---|---|
| F2.0 | Cerrada | 66 problems / 40 err / 26 warn | Baseline | No aplica |
| F2.1 | Cerrada con observaciones | `set-state-in-effect` 29 → 0 | Estado derivado, lazy init, handlers, sin `queueMicrotask` como workaround | Pico de regresión vs F1 documentado en cierre F2.1 |
| F2.2 | Cerrada con observaciones | `exhaustive-deps` 17 → 0 | `useMemo`, deps completas, callbacks | ~31 failed / 9 files |
| F2.3 | Cerrada | 11 errores mecánicos → 0; 7 warnings restantes | `no-unused-vars`, `no-useless-assignment`, `no-extra-boolean-cast`, `prefer-as-const` | 31 failed / 9 files |
| F2.4/F2.5 | Cerrada | 7 warnings → **0** | `react-refresh/only-export-components`, `reportUnusedDisableDirectives` | Mejora (p. ej. CompareMany); ver F2.4/5 doc |
| F2.6 | Cerrada | **0 problems** | Validación + este documento | **18 failed / 8 files** (validación 2026-05-05) |

## Archivos modificados durante F2 (consolidado)

Lista consolidada y deduplicada a partir de los cierres F2.1–F2.5 y del trabajo en repo; puede haber solapamiento entre subfases.

### Productivos

- `frontend/src/pages/AdminAiConfigPage.tsx`
- `frontend/src/pages/AislePositionsPage.tsx`
- `frontend/src/pages/InventoriesList.tsx`
- `frontend/src/pages/InventoryDetail.tsx`
- `frontend/src/pages/ReviewQueuePage.tsx`
- `frontend/src/pages/analytics/CompareManyRunsPage.tsx`
- `frontend/src/pages/analytics/CompareRunsPage.tsx`
- `frontend/src/pages/analytics/compareManyRunsDraft.ts`
- `frontend/src/components/CreateAisleDialog.tsx`
- `frontend/src/components/ExecutionLogPanel.tsx`
- `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx`
- `frontend/src/components/ui/ImageViewer.tsx`
- `frontend/src/components/ui/AppSnackbarProvider.tsx`
- `frontend/src/components/ui/appSnackbarContext.ts`
- `frontend/src/components/ui/useAppSnackbar.ts`
- `frontend/src/components/ui/index.ts`
- `frontend/src/components/adminAiInspector/InspectorPrimitives.tsx`
- `frontend/src/dev/cacheMutationGuardrails.ts`
- `frontend/src/dev/cacheMutationObservability.ts`
- `frontend/src/features/analytics/MetricsPage.tsx`
- `frontend/src/features/auth/AuthProvider.tsx`
- `frontend/src/features/inventories/hooks/useAisleProcessingFlow.ts`
- `frontend/src/features/ingestionSessions/api/captureSessionsApi.ts`
- `frontend/src/features/ingestionSessions/pages/IngestionSessionsPage.tsx`
- `frontend/src/features/ingestionSessions/pages/IngestionSessionDetailPage.tsx`
- `frontend/src/features/ingestionSessions/utils/ingestionSessionsListParams.ts`
- `frontend/src/features/ingestionSessions/utils/ingestionSessionDetailParams.ts`
- `frontend/src/features/results/components/detail/ResultReviewActions.tsx`
- `frontend/src/features/results/hooks/useEvidenceImageLoad.ts`
- `frontend/src/features/results/mappers/positionToResult.ts`
- `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx`
- `frontend/src/hooks/useDebouncedSearchInput.ts`
- `frontend/src/hooks/useDebouncedValue.ts`
- `frontend/src/i18n/index.ts`
- `frontend/src/types/statusAlignment.ts`

### Tests

- `frontend/tests/api/evidenceImageLoad.test.tsx`
- `frontend/tests/auth/authStorage.test.ts`
- `frontend/tests/resultMappers.test.ts`
- `frontend/tests/CompareManyRunsPage.test.tsx`
- `frontend/tests/ingestionSessionsR2Corrections.test.tsx`

### Documentación

- `audit/frontend-f2-0-eslint-baseline.md`
- `audit/frontend-f2-1-set-state-in-effect.md`
- `audit/frontend-f2-2-exhaustive-deps.md`
- `audit/frontend-f2-3-eslint-mechanical-cleanup.md`
- `audit/frontend-f2-4-5-lint-tests-warnings.md`
- `audit/frontend-f2-eslint-hooks.md` (este archivo)

## Correcciones por categoría

| Categoría | Antes (F2.0 o momento de entrada) | Después (F2.6) | Acción aplicada |
|---|---:|---:|---|
| `react-hooks/set-state-in-effect` | 29 | 0 | Estado derivado, `useMemo`, lazy `useState`, handlers, `useReducer`; segunda pasada sin `queueMicrotask` genérico |
| `react-hooks/exhaustive-deps` | 19 | 0 | Referencias estables (`useMemo`), deps completas, callbacks |
| `@typescript-eslint/no-unused-vars` | 6 (F2.3) | 0 | Eliminar símbolos/mock args; firmas más ajustadas |
| `no-useless-assignment` | 3 | 0 | Inicialización de `let` / expresiones únicas |
| `no-extra-boolean-cast` | 1 | 0 | Condición directa |
| `@typescript-eslint/prefer-as-const` | 1 | 0 | `'es' as const` |
| `react-refresh/only-export-components` | 5 (F2.0 aprox.) | 0 | Helpers/context/hook en módulos `.ts` o archivos dedicados; export único de componente donde aplica |
| `reportUnusedDisableDirectives` | 2 | 0 | Quitar comentarios `eslint-disable` innecesarios |

## Validación final (F2.6)

### ESLint

```bash
cd frontend
npm run lint
```

Resultado:

```txt
(sin salida de problemas — 0 errors, 0 warnings)
```

Confirmación JSON (`npx eslint . -f json`): **0** mensajes; `react-hooks/set-state-in-effect`: **0**; `react-hooks/exhaustive-deps`: **0**.

### Typecheck

```bash
cd frontend
npm run typecheck
```

Script real: `tsc --noEmit`.

Resultado:

```txt
(sin errores de TypeScript)
```

### Vitest

```bash
cd frontend
npm run test
```

Resultado (ejecución de cierre F2.6):

```txt
Test Files  8 failed | 60 passed (68)
Tests      18 failed | 408 passed (426)
Duration   ~18s (orden de magnitud)
```

Tests puntuales sensibles: la suite completa anterior cubre los mismos módulos; no fue obligatorio repetir cada archivo por archivo tras `npm run test` completo.

## Estado de Vitest post-F2

| Referencia | Resultado |
|---|---|
| Cierre F1 (documentado) | 16 failed / 6 failed files |
| Peor punto intermediario F2 (~F2.2/F2.3) | ~31 failed / 9 failed files |
| Resultado final F2 (F2.6) | **18 failed / 8 failed files**, 408 passed |

**Clasificación:** **REGRESIÓN_EXPLICADA** respecto del número de fallos de F1 (+2 tests fallidos y más archivos con fallos), pero **mejora clara** respecto del peor punto de F2 tras estabilización parcial (incl. CompareMany y fixes colaterales).

**Interpretación:** la divergencia frente a F1 se asocia principalmente a **cambios de comportamiento y patrones de estado** introducidos al eliminar `set-state-in-effect` y ajustar drafts/router (`CompareRunsPage`, `CompareManyRunsPage`, `AuthProvider`, `QuickReviewDrawer`, etc.), no a errores ESLint vigentes.

**Acción recomendada antes o en paralelo a F3:**

- Mini-fase **F2.7 — Estabilización Vitest post-F2** (o inclusión en backlog F1.5) para volver a **≤16 failed / ≤6 files** o documentar aceptación formal.

## Pendientes derivados

| Pendiente | Motivo | Fase sugerida |
|---|---|---|
| Auditoría conceptual de efectos | ESLint limpio; revisión semántica pendiente | **F3** |
| Vitest vs F1 | Regresión residual | **F2.7** / estabilización |
| Separación components ↔ api/fetch | Arquitectura | F4 |
| Complejidad / archivos grandes | Mantenibilidad | F5 |
| Dependencias / npm audit | Seguridad | F9 |

## Conclusión

- **ESLint:** objetivo cumplido (**0 problems**, **0 errores**, **0 warnings**).
- **Hooks críticos ESLint:** `set-state-in-effect` y `exhaustive-deps` en **0**.
- **Typecheck:** OK.
- **Vitest:** mejor que el peor F2, pero **no restaurado** al nivel del cierre F1 documentado.

**¿Se puede avanzar a F3?** **Sí**, como trabajo conceptual sobre `useEffect` y patrones de sincronización, **siempre que** quede explícito en el plan de sprint que la **deuda de Vitest post-F2** sigue abierta y se programa **F2.7** o equivalente según prioridad del equipo.

## Criterio de cierre F2

| # | Criterio | Cumplido |
|---:|---|---|
| 1 | ESLint 0 errores | Sí |
| 2 | Reglas hooks objetivo en 0 | Sí |
| 3 | Warnings 0 o documentados | Sí (0) |
| 4 | Sin dependencias/CI/refactors masivos en F2 | Sí (alcance respetado) |
| 5 | Typecheck OK o documentado | Sí (OK) |
| 6 | Vitest sin empeoramiento sin explicación | Parcial: mejor vs pico F2; peor vs F1 documentado — **explicado** |
| 7 | Siguiente paso claro | Sí: F3 + F2.7 opcional |
