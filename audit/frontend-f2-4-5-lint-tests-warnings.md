# Fase F2.4/F2.5 — Lint en tests y warnings no bloqueantes

## Estado

F2.4/F2.5 CERRADA

## Resumen ejecutivo

- Baseline inicial ESLint (cierre F2.3): 7 problems (0 errors, 7 warnings)
- Resultado final ESLint: **0 problems**
- Errors iniciales: 0
- Errors finales: 0
- Warnings iniciales: 7
- Warnings finales: 0
- Tests con hallazgos ESLint (mensajes en `frontend/tests/**`): **0** (`test_messages: 0` en salida JSON de ESLint)
- Warnings corregidos: 7 (5 × `react-refresh/only-export-components`, 2 × `reportUnusedDisableDirectives`)
- Warnings derivados: 0
- Codigo productivo modificado: multiples archivos (split snackbar, helpers extraidos, `ExecutionLogPanel`, dev sin disables muertos, `CompareManyRunsPage` orden de drafts)
- Tests modificados: imports mecanicos en `CompareManyRunsPage.test.tsx`, `ingestionSessionsR2Corrections.test.tsx`
- Hooks: `react-hooks/set-state-in-effect: 0`, `react-hooks/exhaustive-deps: 0`
- Resultado Vitest suite completa: **18 failed | 408 passed** (8 failed files) — mejor que F2.3 (`31 failed`), sin empeoramiento

## Confirmacion F2.4 — Tests

| Area | Resultado |
|---|---|
| `frontend/tests/**` | Sin errores ESLint; sin warnings ESLint en esta pasada |
| Errores en tests | 0 |
| Warnings en tests | 0 |

F2.4 queda cerrada porque no quedan errores ESLint en tests.

## Warnings revisados F2.5

| Archivo | Regla | Decision | Motivo |
|---|---|---|---|
| `ExecutionLogPanel.tsx` | `react-refresh/only-export-components` | CORREGIR_AHORA | `getReadableErrorMessage` solo se usaba en el mismo modulo; se dejo como funcion interna sin export |
| `AppSnackbarProvider.tsx` + nuevos modulos | `react-refresh/only-export-components` | CORREGIR_AHORA | Contexto en `appSnackbarContext.ts`, hook en `useAppSnackbar.ts`, Provider solo exporta componente |
| `IngestionSessionsPage.tsx` | `react-refresh/only-export-components` | CORREGIR_AHORA | `buildSessionsListParams` movido a `utils/ingestionSessionsListParams.ts` |
| `IngestionSessionDetailPage.tsx` | `react-refresh/only-export-components` | CORREGIR_AHORA | `hasRequiredDetailParams` movido a `utils/ingestionSessionDetailParams.ts` |
| `CompareManyRunsPage.tsx` | `react-refresh/only-export-components` | CORREGIR_AHORA | Constantes + `buildDraftError` en `compareManyRunsDraft.ts`; eliminado `__testables` |
| `cacheMutationGuardrails.ts` | `reportUnusedDisableDirectives` | CORREGIR_AHORA | Eliminado `eslint-disable-next-line no-console` innecesario |
| `cacheMutationObservability.ts` | `reportUnusedDisableDirectives` | CORREGIR_AHORA | Igual para `console.debug` |

## Archivos modificados

| Archivo | Tipo | Motivo |
|---|---|---|
| `frontend/src/components/ui/appSnackbarContext.ts` | Productivo (nuevo) | Contexto + tipos snackbar |
| `frontend/src/components/ui/useAppSnackbar.ts` | Productivo (nuevo) | Hook fuera del archivo del Provider |
| `frontend/src/components/ui/AppSnackbarProvider.tsx` | Productivo | Solo Provider |
| `frontend/src/components/ui/index.ts` | Productivo | Re-export desde nuevos modulos |
| `frontend/src/components/adminAiInspector/InspectorPrimitives.tsx` | Productivo | Import directo de `useAppSnackbar` |
| `frontend/src/components/ExecutionLogPanel.tsx` | Productivo | Quitar export no usado de helper |
| `frontend/src/pages/analytics/compareManyRunsDraft.ts` | Productivo (nuevo) | Draft validation + constantes compare-many |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | Productivo | Import draft helpers; **orden de `draft*` antes de `jobsQuery`** (TDZ) |
| `frontend/src/features/ingestionSessions/utils/ingestionSessionsListParams.ts` | Productivo (nuevo) | Helper list params |
| `frontend/src/features/ingestionSessions/utils/ingestionSessionDetailParams.ts` | Productivo (nuevo) | Helper detail guards |
| `frontend/src/features/ingestionSessions/pages/IngestionSessionsPage.tsx` | Productivo | Import helper |
| `frontend/src/features/ingestionSessions/pages/IngestionSessionDetailPage.tsx` | Productivo | Import helper |
| `frontend/src/dev/cacheMutationGuardrails.ts` | Productivo | Quitar disable muerto |
| `frontend/src/dev/cacheMutationObservability.ts` | Productivo | Quitar disable muerto |
| `frontend/tests/CompareManyRunsPage.test.tsx` | Test | Import `buildDraftError` desde modulo dedicado |
| `frontend/tests/ingestionSessionsR2Corrections.test.tsx` | Test | Imports desde `utils/*` |
| `audit/frontend-f2-4-5-lint-tests-warnings.md` | Documentacion | Cierre |

## Observacion — CompareManyRunsPage

Durante la validacion se detecto que `draftAisleId` / `draftJobIds` / `draftBaseline` se usaban en `useAisleJobsList` **antes** de declararse (TDZ en runtime). Se movio el bloque `draftSourceKey` + drafts **encima** de `inventoryQuery` / `jobsQuery`. Cambio minimo de orden, sin alterar formulas.

## Validacion ejecutada

### ESLint

```bash
cd frontend
npm run lint
```

Resultado:

```txt
(sin salida de problemas — 0 errors, 0 warnings)
```

### Vitest

```bash
cd frontend
npm run test
```

Resultado (resumen):

```txt
Test Files  8 failed | 60 passed (68)
Tests      18 failed | 408 passed (426)
```

## Pendientes derivados

| Pendiente | Motivo | Fase sugerida |
|---|---|---|
| Vitest 18 fallos restantes | Auth, mocks ingestion, QuickReview anchor, etc.; fuera de alcance lint | Estabilizacion / F2.6 |

## Criterio de cierre

1. Sin errores ESLint en tests.
2. Warnings revisados y corregidos (triviales) o derivados (ninguno derivado).
3. ESLint 0 errores.
4. Hooks sin regresion.
5. Sin refactors grandes (solo extracciones locales y reorder TDZ).
6. Vitest no empeoro respecto a F2.3.
