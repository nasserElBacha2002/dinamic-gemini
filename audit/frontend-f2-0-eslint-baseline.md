# Fase F2.0 - Baseline ESLint frontend

## Estado

F2.0 CERRADA

## Resumen ejecutivo

- Comando utilizado: `cd frontend && npm run lint` (script real: `lint: eslint .`).
- Estado general: baseline reconfirmada y comparable contra F0.
- Problems: 66.
- Errors: 40.
- Warnings: 26.
- Diferencia contra F0: sin cambios (`66/40/26` en ambos cortes).
- Riesgo principal: concentración de errores en `react-hooks/set-state-in-effect` (29 errores).
- Recomendacion para F2.1: iniciar por hooks con setState en efectos en paginas/componentes de mayor impacto operativo.

## Fuentes revisadas

- `audit/raw/frontend-eslint.txt`
- `audit/audit-summary.md`
- `audit/audit-status.json`
- `audit/frontend-f0-normalization.md`
- `audit/frontend-f1-tests-stabilization.md`
- `frontend/package.json`
- `frontend/eslint.config.js`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`

## Resultado de ESLint actual

```bash
cd frontend
npm run lint
```

Resultado resumido:

```txt
> dinamic-inventory-v3-frontend@0.1.0 lint
> eslint .

✖ 66 problems (40 errors, 26 warnings)
1 error and 2 warnings potentially fixable with the --fix option.
```

Observaciones de ejecucion:

- Se detecto primero un intento invalido por contexto de directorio; la corrida valida para baseline fue la ejecutada en `frontend`.
- El comando no usa `--max-warnings`; no corta por warnings, corta por exit code 1 debido a errores.

## Comparacion contra F0

| Metrica | F0 | F2.0 actual | Diferencia |
| --- | ---: | ---: | ---: |
| Problems | 66 | 66 | 0 |
| Errors | 40 | 40 | 0 |
| Warnings | 26 | 26 | 0 |

Conclusion de comparacion:

- La senal de ESLint se mantiene estable respecto de F0.
- No hay evidencia de aumento o reduccion neta posterior al cierre F1.
- La prioridad de F2 se mantiene intacta.

## Hallazgos por regla

| Regla | Cantidad | Errors | Warnings | Riesgo | Subfase sugerida |
| --- | ---: | ---: | ---: | --- | --- |
| `react-hooks/set-state-in-effect` | 29 | 29 | 0 | ALTO | F2.1 |
| `react-hooks/exhaustive-deps` | 19 | 0 | 19 | ALTO/MEDIO | F2.2 |
| `@typescript-eslint/no-unused-vars` | 6 | 6 | 0 | BAJO | F2.3 |
| `react-refresh/only-export-components` | 5 | 0 | 5 | BAJO | F2.5 |
| `no-useless-assignment` | 3 | 3 | 0 | BAJO | F2.3 |
| `reportUnusedDisableDirectives` | 2 | 0 | 2 | BAJO | F2.5 |
| `no-extra-boolean-cast` | 1 | 1 | 0 | BAJO | F2.3 |
| `@typescript-eslint/prefer-as-const` | 1 | 1 | 0 | BAJO | F2.3 |

Notas:

- En esta baseline no aparecieron hallazgos para: `@typescript-eslint/no-unused-expressions`, `@typescript-eslint/no-unnecessary-condition`, `@typescript-eslint/no-unnecessary-boolean-literal-compare`, `@typescript-eslint/no-useless-empty-export`, `@typescript-eslint/no-inferrable-types`, `prefer-const`, `no-empty`.
- No se detectan reglas a `DERIVAR_F3/F5/F10` en esta corrida puntual; los warnings de `exhaustive-deps` quedan en F2.2 con posible derivacion posterior solo si el fix exigiera cambio conceptual mayor.

## Hallazgos por archivo

| Archivo | Errors | Warnings | Reglas principales | Subfase sugerida |
| --- | ---: | ---: | --- | --- |
| `frontend/src/pages/AislePositionsPage.tsx` | 2 | 6 | `react-hooks/exhaustive-deps`, `react-hooks/set-state-in-effect` | F2.1/F2.2 |
| `frontend/src/components/ExecutionLogPanel.tsx` | 3 | 4 | `react-hooks/set-state-in-effect`, `react-hooks/exhaustive-deps` | F2.1/F2.2 |
| `frontend/src/pages/ReviewQueuePage.tsx` | 3 | 3 | `react-hooks/set-state-in-effect`, `react-hooks/exhaustive-deps` | F2.1/F2.2 |
| `frontend/src/features/analytics/MetricsPage.tsx` | 4 | 1 | `react-hooks/set-state-in-effect`, `no-extra-boolean-cast` | F2.1/F2.3 |
| `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx` | 4 | 1 | `react-hooks/set-state-in-effect`, `@typescript-eslint/no-unused-vars` | F2.1/F2.3 |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | 1 | 2 | `react-hooks/set-state-in-effect`, `react-hooks/exhaustive-deps` | F2.1/F2.2 |
| `frontend/src/pages/analytics/CompareRunsPage.tsx` | 2 | 1 | `react-hooks/set-state-in-effect`, `react-hooks/exhaustive-deps` | F2.1/F2.2 |
| `frontend/src/features/ingestionSessions/api/captureSessionsApi.ts` | 2 | 0 | `no-useless-assignment` | F2.3 |
| `frontend/tests/api/evidenceImageLoad.test.tsx` | 2 | 0 | `@typescript-eslint/no-unused-vars` | F2.4 |
| `frontend/tests/auth/authStorage.test.ts` | 1 | 0 | `@typescript-eslint/no-unused-vars` | F2.4 |

## Errores bloqueantes

- `react-hooks/set-state-in-effect` (29): bloqueante principal para F2 por impacto potencial en flujo de render y estabilidad de hooks.
- `@typescript-eslint/no-unused-vars` (6): errores mecanicos, incluye `frontend/tests/**`.
- `no-useless-assignment` (3): errores mecanicos de asignaciones no usadas.
- `no-extra-boolean-cast` (1): error mecanico.
- `@typescript-eslint/prefer-as-const` (1): error mecanico.

## Warnings no bloqueantes

| Warning | Archivo (principal) | Clasificacion preliminar |
| --- | --- | --- |
| `react-hooks/exhaustive-deps` | `frontend/src/pages/AislePositionsPage.tsx` y otros | CORREGIR_EN_F2 |
| `react-refresh/only-export-components` | `frontend/src/components/ExecutionLogPanel.tsx` y otros | ACEPTAR_TEMPORALMENTE |
| `reportUnusedDisableDirectives` | `frontend/src/dev/cacheMutationGuardrails.ts` y `frontend/src/dev/cacheMutationObservability.ts` | CORREGIR_EN_F2 |

## Priorizacion recomendada

1. F2.1 - Corregir `react-hooks/set-state-in-effect` empezando por archivos con mayor densidad y criticidad de flujo (`MetricsPage`, `QuickReviewDrawer`, `ExecutionLogPanel`, `ReviewQueuePage`, `AislePositionsPage`).
2. F2.2 - Resolver `react-hooks/exhaustive-deps` en paginas con filtros/paginacion y derivar solo los casos que requieran rediseño conceptual.
3. F2.3 - Cerrar errores mecanicos de ESLint en `src` (`no-unused-vars`, `no-useless-assignment`, `no-extra-boolean-cast`, `prefer-as-const`).
4. F2.4 - Limpiar lint puntual en tests (`frontend/tests/api/evidenceImageLoad.test.tsx`, `frontend/tests/auth/authStorage.test.ts`).
5. F2.5 - Tratar warnings no bloqueantes restantes y decidir aceptaciones temporales documentadas.
6. F2.6 - Cierre global de F2 con corrida final de ESLint y comparacion contra baseline F2.0.

## Exclusiones explicitas

En F2.0 no se corrigio codigo productivo, tests, mocks, dependencias, ESLint ni arquitectura.

## Criterio de cierre

F2.0 se considera cerrada porque:

1. Se identifico el comando real de ESLint.
2. Se ejecuto ESLint en frontend y se documento salida.
3. Se comparo contra F0.
4. Se clasificaron hallazgos por regla.
5. Se clasificaron hallazgos por subfase.
6. No se modifico codigo productivo ni tests.
