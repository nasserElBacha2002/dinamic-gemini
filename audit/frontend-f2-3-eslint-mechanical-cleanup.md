# Fase F2.3 — Limpieza mecanica ESLint frontend

## Estado

F2.3 CERRADA

## Resumen ejecutivo

- Baseline inicial ESLint (cierre F2.2): 18 problems (11 errors, 7 warnings)
- Resultado final ESLint: 7 problems (0 errors, 7 warnings)
- Errores iniciales: 11
- Errores finales: 0
- Warnings iniciales: 7
- Warnings finales: 7 (sin cambio; fuera de alcance F2.3)
- Reglas corregidas: `@typescript-eslint/no-unused-vars`, `no-useless-assignment`, `no-extra-boolean-cast`, `@typescript-eslint/prefer-as-const`
- Archivos productivos modificados: 8
- Tests modificados: 3 (solo ajuste mecanico / firma / lint)
- Confirmacion hooks: `react-hooks/set-state-in-effect: 0`, `react-hooks/exhaustive-deps: 0`
- Resultado Vitest suite completa: `31 failed | 395 passed` (9 failed files) — igual que F2.2, sin empeoramiento

## Archivos modificados

| Archivo | Tipo | Regla | Motivo |
|---|---|---|---|
| `frontend/src/features/analytics/MetricsPage.tsx` | Productivo | `no-extra-boolean-cast` | Quitar `Boolean()` redundante en ternario |
| `frontend/src/features/ingestionSessions/api/captureSessionsApi.ts` | Productivo | `no-useless-assignment` | Inicializacion `let` sin asignacion previa inutil |
| `frontend/src/features/results/hooks/useEvidenceImageLoad.ts` | Productivo | `no-unused-vars` | Parametro `detail` no usado en `messageForKind` |
| `frontend/src/features/results/mappers/positionToResult.ts` | Productivo | `no-unused-vars` | Eliminar indice no usado en `mapEvidenceToResultEvidence` |
| `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx` | Productivo | `no-unused-vars` | Omitir `job_id` con copia + `delete` en lugar de destructuring con binding muerto |
| `frontend/src/i18n/index.ts` | Productivo | `prefer-as-const` | `fallback` como `'es' as const` |
| `frontend/src/types/statusAlignment.ts` | Productivo | `no-useless-assignment` | `traceabilityTarget` como expresion constante (sin asignaciones secuenciales inutiles) |
| `frontend/tests/api/evidenceImageLoad.test.tsx` | Test | `no-unused-vars` | Mock `fetch` sin parametros no usados |
| `frontend/tests/auth/authStorage.test.ts` | Test | `no-unused-vars` | Quitar import `vi` no usado |
| `frontend/tests/resultMappers.test.ts` | Test | - | Alinear llamadas con nueva firma de `mapEvidenceToResultEvidence` |
| `audit/frontend-f2-3-eslint-mechanical-cleanup.md` | Documentacion | - | Cierre |

## Correcciones por regla

| Regla | Antes | Despues | Accion aplicada |
|---|---:|---:|---|
| `@typescript-eslint/no-unused-vars` | 6 | 0 | Eliminar imports/parametros no usados; ajustar mocks de test; firma de mapper |
| `no-useless-assignment` | 3 | 0 | `let` sin valor inicial redundante; expresion constante para `traceabilityTarget` |
| `no-extra-boolean-cast` | 1 | 0 | Condicion directa sin `Boolean(...)` |
| `@typescript-eslint/prefer-as-const` | 1 | 0 | Literal con `as const` |

## Validacion ejecutada

### ESLint

```bash
cd frontend
npm run lint
```

Resultado:

```txt
7 problems (0 errors, 7 warnings)
```

Hooks (desde salida JSON de eslint):

```txt
react-hooks/set-state-in-effect: 0
react-hooks/exhaustive-deps: 0
```

### Tests

```bash
cd frontend
npm run test -- tests/MetricsPage.test.tsx tests/QuickReviewDrawer.test.tsx tests/api/evidenceImageLoad.test.tsx tests/resultMappers.test.ts
```

Resultado: 4 archivos, 80 tests pasados.

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

| Pendiente | Motivo | Fase sugerida |
|---|---|---|
| `react-refresh/only-export-components` | Warning no bloqueante | F2.5 |
| `reportUnusedDisableDirectives` (dev) | Warning no bloqueante | F2.5 |
| Vitest 31 fallos | Fuera de alcance F2.3 | Estabilizacion / F2.6 |

## Observaciones

- No se tocaron `package.json`, rutas, copy/i18n ni contratos API.
- `QuickReviewDrawer`: mismo comportamiento de payload (sin `job_id` cuando no hay storage job); implementacion evita variable de destructuring no leida.
- `mapEvidenceToResultEvidence`: la segunda posicion de `.map()` se ignora por JS; las pruebas se actualizaron para no pasar indice redundante.

## Criterio de cierre

1. Errores mecanicos (`no-unused-vars`, `no-useless-assignment`, `no-extra-boolean-cast`, `prefer-as-const`) en 0.
2. Hooks F2.1/F2.2 sin regresion.
3. Sin refactors grandes ni cambios de UX.
4. Vitest no empeoro respecto a F2.2.
