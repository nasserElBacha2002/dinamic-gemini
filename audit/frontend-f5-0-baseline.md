# F5.0 — Baseline previo a reduccion de complejidad

## Resumen ejecutivo
- Estado final: LISTO_CON_OBSERVACIONES
- Fecha: 2026-05-06
- Rama/commit: `DIN-091` / `a79cd8a`
- Conclusion: El frontend queda con typecheck/lint en verde, cierre F4 confirmado para acoplamiento UI->API/fetch en componentes objetivo, y baseline de complejidad actualizado. La suite global de Vitest mantiene fallas preexistentes fuera del alcance F4/F5.0.

## Validaciones
| Comando | Resultado | Observaciones |
|---|---|---|
| `git status --short` | OK | Working tree limpio (sin cambios pendientes). |
| `npm run typecheck` | OK | Sin errores. |
| `npm run lint` | OK | Sin errores. |
| `npm test -- --run` | Falla | `6 failed | 62 passed` suites; `8 failed | 418 passed` tests. Fallas no relacionadas con desacople F4. |
| `npm test -- --run CreateInventoryDialog.visualReferences` | OK | `9 passed`. Suite estabilizada. |
| `npm test -- --run CreateInventoryDialog` | OK | `9 passed`. |
| `npm test -- --run CreateAisleDialog` | OK | `3 passed`. |
| `npm test -- --run ReferenceImagesDrawer` | OK | `10 passed`; warning no bloqueante `validateDOMNesting(<h6> dentro de <h2>)`. |
| `npm test -- --run ManagedImageAssetsDrawer` | OK | `2 passed`; warning no bloqueante `validateDOMNesting(<h6> dentro de <h2>)`. |
| `npm test -- --run ExecutionLogPanel` | OK | `8 passed`. |
| `npm test -- --run CompareRunJobPickers` | Observacion | Vitest: `No test files found` (no se trata como falla funcional). |

## Estado F4 verificado
| Verificacion | Resultado | Observaciones |
|---|---|---|
| Imports directos `api/client` en 8 componentes F4 | OK | Sin matches para `from .*api/client` en: `ExecutionLogPanel`, `TraceabilityChip`, `CreateAisleDialog`, `ReferenceImagesDrawer`, `CompareRunJobPickers`, `AisleObservabilityDialog`, `ManagedImageAssetsDrawer`, `CreateInventoryDialog`. |
| `fetch(` nativo en 8 componentes F4 | OK con observacion | Sin `fetch(` nativo. Solo aparecen `refetch()` de TanStack Query en `AisleObservabilityDialog` (aceptable). |

## Tests
| Suite | Resultado | Observaciones |
|---|---|---|
| `tests/CreateInventoryDialog.visualReferences.test.tsx` | OK | Verde luego de ajuste de selectores accesibles alineados al mock/i18n actual. |
| `tests/ingestionSessionsR2Corrections.test.tsx` | Falla | 2 tests fallidos (preexistente baseline global). |
| `tests/AdminAiConfigPage.test.tsx` | Falla | 2 tests fallidos (preexistente baseline global). |
| `tests/QuickReviewDrawer.anchorSync.test.tsx` | Falla | 1 test fallido (preexistente baseline global). |
| `tests/PromoteOperationalDialog.test.tsx` | Falla | 1 test fallido (preexistente baseline global). |
| `tests/CompareRunsDialog.test.tsx` | Falla | 1 test fallido (preexistente baseline global). |
| `tests/AppShellAdminNav.test.tsx` | Falla | 1 test fallido (preexistente baseline global). |

## Complejidad actuala
| Archivo | Lineas aprox | Prioridad F5 | Accion futura |
|---|---:|---|---|
| `frontend/src/features/analytics/MetricsPage.tsx` | 1167 | Alta | Separar secciones/estado derivado en modulos por dominio visual. |
| `frontend/src/api/client.ts` | 1131 | Alta | Extraer por dominios API manteniendo contrato publico estable. |
| `frontend/src/pages/AislePositionsPage.tsx` | 869 | Alta | Extraer hooks de orquestacion y bloques UI por panel. |
| `frontend/src/api/types/responses.ts` | 816 | Alta | Particionar tipos por dominio y reexport central. |
| `frontend/src/components/ExecutionLogPanel.tsx` | 678 | Media-Alta | Extraer subcomponentes de vistas y utilidades de formateo. |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | 657 | Media-Alta | Aislar sync URL/estado y bloques de rendering. |
| `frontend/src/pages/AdminAiConfigPage.tsx` | 626 | Media-Alta | Extraer loaders/acciones y secciones de formulario. |
| `frontend/src/pages/analytics/CompareRunsPage.tsx` | 594 | Media | Separar presentacion, filtros y sync URL. |
| `frontend/src/features/ingestionSessions/components/ImportSessionGroupingPanel.tsx` | 531 | Media | Dividir secciones de tabla/acciones y helpers. |
| `frontend/src/pages/ReviewQueuePage.tsx` | 529 | Media | Extraer coordinacion de filtros/acciones y paneles. |
| `frontend/src/components/CreateInventoryDialog.tsx` | 526 | Media | Separar pasos y utilidades de archivos sin tocar flujo UX. |
| `frontend/src/hooks/reviewActionCachePatch.ts` | 508 | Media | Particionar estrategias de patch por tipo de accion. |
| `frontend/src/features/results/components/detail/ResultReviewActions.tsx` | 471 | Media | Extraer handlers y secciones por tipo de accion. |
| `frontend/src/components/AisleObservabilityDialog.tsx` | 463 | Media | Separar queries/acciones y bloques visuales. |
| `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx` | 411 | Media | Extraer vistas de lista/preview y helpers de estado. |
| `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx` | 394 | Media | Extraer sincronizacion anchor/estado y paneles UI. |

## Riesgos antes de F5.1
- Suite global con 8 tests fallidos preexistentes puede enmascarar regresiones si no se mantiene set focalizado por dominio.
- Warnings recurrentes de React Router future flags y `validateDOMNesting` agregan ruido en salida de pruebas.
- `api/client.ts` y `responses.ts` concentran superficie alta; dividir sin estrategia de compatibilidad puede romper imports internos.

## Recomendacion
- LISTO_CON_OBSERVACIONES
