# F5 — Cierre reducción de complejidad frontend

## Resumen ejecutivo
- Estado final: **F5 CERRADA_CON_OBSERVACIONES**
- Fecha: 2026-05-06
- Rama/commit: `DIN-091` / `98b4494`
- Conclusión: F5 cumple su objetivo de reducción estructural con guardrails preservados. `typecheck` y `lint` pasan; tests focalizados principales pasan. Persisten fallas preexistentes conocidas fuera del alcance de F5.

## Reducción de tamaño
| Archivo | Líneas baseline F5.0 | Líneas final F5.5 | Reducción | Observación |
|---|---:|---:|---:|---|
| `frontend/src/api/client.ts` | 1131 | 81 | -1050 (~92.8%) | Consolidado como fachada compatible por dominio |
| `frontend/src/features/analytics/MetricsPage.tsx` | 1167 | 610 | -557 (~47.7%) | Mantiene orquestación; UI y derivados fueron extraídos |
| `frontend/src/pages/AislePositionsPage.tsx` | 869 | 691 | -178 (~20.5%) | Mantiene orquestación sensible (URL/query/acciones) |
| `frontend/src/pages/analytics/CompareRunsPage.tsx` | 594 | 309 | -285 (~48.0%) | Mantiene URL sync/navigation/export/query hooks en página |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | 657 | 345 | -312 (~47.5%) | Mantiene canonicalización y doble-query en página |

## Distribución de extracciones (líneas)

### API por dominio
- `frontend/src/api/http.ts`: 72
- `frontend/src/api/inventoriesApi.ts`: 170
- `frontend/src/api/aislesApi.ts`: 165
- `frontend/src/api/jobsApi.ts`: 232
- `frontend/src/api/assetsApi.ts`: 153
- `frontend/src/api/analyticsApi.ts`: 157
- `frontend/src/api/adminAiApi.ts`: 31
- `frontend/src/api/reviewQueueApi.ts`: 111

### Adapters principales de F5
- `frontend/src/features/analytics/adapters/metricsFormatters.ts`: 122
- `frontend/src/features/analytics/adapters/metricsViewModel.ts`: 275
- `frontend/src/features/results/adapters/aislePositionsViewModel.ts`: 52
- `frontend/src/features/results/adapters/aislePositionsFormatters.ts`: 13
- `frontend/src/features/analytics/adapters/compareFormatters.ts`: 127
- `frontend/src/features/analytics/adapters/compareRunsViewModel.ts`: 35
- `frontend/src/features/analytics/adapters/compareManyRunsViewModel.ts`: 110

### Componentes por feature (resumen)
- `frontend/src/features/analytics/components/*`: 1517 líneas totales
- `frontend/src/features/results/components/*`: 2160 líneas totales

## Extracciones por fase
| Fase | Área | Archivos principales | Resultado |
|---|---|---|---|
| F5.1 | `api/client.ts` | `api/*Api.ts`, `api/http.ts` | `client.ts` queda como façade compatible |
| F5.2 | Metrics | analytics adapters/components | página más chica y enfocada en orquestación |
| F5.3 | Results | results adapters/components | reducción con page como orquestador sensible |
| F5.4 | Compare pages | compare adapters/components | páginas más chicas; URL/query/navigation quedan en page |
| F5.5 | Validación/cierre | auditoría y pruebas | cierre con evidencia y guardrails confirmados |

## Validaciones
| Comando | Resultado | Observaciones |
|---|---|---|
| `npm run typecheck` | OK | sin errores |
| `npm run lint` | OK | sin errores |
| `npm test -- --run MetricsPage` | OK | 13/13 |
| `npm test -- --run AislePositionsPage` | OK | 20/20 |
| `npm test -- --run CompareRunsPage` | OK | 13/13 |
| `npm test -- --run CompareManyRunsPage` | OK | 15/15 |
| `npm test -- --run CreateInventoryDialog` | OK | 9/9 |
| `npm test -- --run CreateAisleDialog` | OK | 3/3 |
| `npm test -- --run ExecutionLogPanel` | OK | 8/8 |
| `npm test -- --run ReferenceImagesDrawer` | OK | 10/10 |
| `npm test -- --run ManagedImageAssetsDrawer` | OK | 2/2 |
| `npm test -- --run ReviewQueuePage` | OK | 3/3 |
| `npm test -- --run ResultReviewActions` | OK | 5/5 |
| `npm test -- --run QuickReviewDrawer` | Falla preexistente | 1 falla (`QuickReviewDrawer.anchorSync`) |
| `npm test -- --run CompareRunsDialog` | Falla preexistente | 1 falla (`/read-only/i`) |
| `npm test -- --run PromoteOperationalDialog` | Falla preexistente | 1 falla (`/operational slice/i`) |
| `npm test -- --run AdminAiConfigPage` | Falla preexistente | 2 fallas |
| `npm test -- --run AppShellAdminNav` | Falla preexistente | 1 falla |
| `npm test -- --run ingestionSessionsR2Corrections` | Falla preexistente | 2 fallas |
| `npm test -- --run` | Con observaciones | 68 suites: 6 fallidas / 62 OK; 426 tests: 8 fallidos / 418 OK |

## Guardrails confirmados
| Área | Estado | Observación |
|---|---|---|
| Endpoints/API | Sin cambios funcionales | sin evidencia de cambios de contrato en F5.5 |
| Query params | Sin cambios funcionales | no se alteran en cierre F5.5 |
| Cache/query hooks | Sin cambios funcionales | sin refactors nuevos en F5.5 |
| Navegación/URL sync | Sin cambios funcionales | sin cambios en cierre F5.5 |
| UX/copy/estilos | Sin cambios funcionales | F5.5 fue validación/documentación |
| Scope de fases | OK | sin mezcla nueva de F6/F7/F8/F9 en esta fase de cierre |

## Validaciones de boundaries y fachada
- `rg "from .*api/client" frontend/src frontend/tests`: hay consumo permitido de fachada (esperado).
- `rg "from ['\"].*client['\"]" frontend/src/api`: sin imports runtime desde módulos dominio hacia `client.ts` (esperado).
- `ls frontend/src/api | rg "captureSessions"`: sin duplicado de `captureSessions` en `api/`.
- Components/adapters extraídos de compare y results: sin imports runtime de API/routing/cache sensibles en los nuevos bloques de compare; en results/analytics hay referencias existentes de tipado o hooks preexistentes fuera del alcance de cierre F5.5.

## Fallas preexistentes
Persisten sin evidencia de regresión nueva de F5:
- `AdminAiConfigPage`: 2
- `AppShellAdminNav`: 1
- `CompareRunsDialog`: 1
- `PromoteOperationalDialog`: 1
- `QuickReviewDrawer.anchorSync`: 1
- `ingestionSessionsR2Corrections`: 2

Estas mismas categorías ya estaban documentadas previamente como deuda de test global.

## Pendientes fuera de F5
- F6: manejo de errores frontend.
- F7: componentes reutilizables.
- F8: dead code.
- F9: dependencias/vulnerabilidades moderadas.
- Posible migración futura de imports desde `api/client.ts` hacia módulos por dominio (si se decide).
- Posible consolidación de `API_BASE` en `api/http.ts` (si aplica).
- Posibles hooks adicionales solo para casos con beneficio claro y bajo riesgo.
- Resolver fallas de tests preexistentes listadas arriba.

## Estado final recomendado
**F5 CERRADA_CON_OBSERVACIONES**

Motivo:
1. Reducción estructural lograda en los 5 objetivos principales.
2. Organización por dominio/capa lograda.
3. Sin cambios funcionales introducidos en esta fase de cierre.
4. `typecheck` y `lint` en verde.
5. Tests focalizados principales en verde.
6. Fallas globales remanentes están documentadas como preexistentes.
7. Se puede avanzar a F6.
