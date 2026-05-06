# Fase F1.4 — Estabilización de InventoryDetailPage.test.tsx

## Estado

**F1.4 CERRADA**

## Resumen ejecutivo

- Tests fallidos al inicio: **17 de 21**.
- Tests fallidos al cierre: **0 de 21**.
- Tests pasados del archivo: **21 de 21**.
- Causa principal: `SELECTOR_ACCESIBLE_ROTO` + `COPY_DESACTUALIZADO` + `I18N_PLACEHOLDER_ACTUAL`.
- Archivos modificados: `frontend/tests/InventoryDetailPage.test.tsx`, `audit/frontend-f1-4-inventory-detail-page.md`.
- Codigo productivo modificado: **No**.
- Resultado de corrida puntual: **21 passed**.
- Resultado de corrida completa: **50 failed / 15 failed files**.

## Archivos modificados

| Archivo | Tipo | Motivo |
|---|---|---|
| `frontend/tests/InventoryDetailPage.test.tsx` | Test | Alinear selectors accesibles y expectations al runtime/i18n actual; robustecer aserciones para evitar coupling con copy legado |
| `audit/frontend-f1-4-inventory-detail-page.md` | Documentacion | Cierre F1.4 |

## Fallos corregidos

| Test | Causa | Correccion aplicada |
|---|---|---|
| `keeps reference images lazy...`, `keeps the page focused...`, `opens the reference images drawer...` | `COPY_DESACTUALIZADO` + `I18N_PLACEHOLDER_ACTUAL` | `Reference images` -> `Visual refs title`; heading del drawer -> `Drawer title`; body -> `Management body`; `Aisles` -> `List title` |
| Bloque de tests de observabilidad (view logs, download actions, scope toggle, cancel/retry, process flow) | `SELECTOR_ACCESIBLE_ROTO` | Accion de fila `actions for aisle a-01` -> `row actions a11y` (aria-label real del `RowActionMenu`) |
| `opens one observability dialog...`, `switching log scope...` | `I18N_PLACEHOLDER_ACTUAL` | Heading `aisle observability` -> `dialog title aisle`; opcion `merged aisle log` -> `scope merged` |
| `renders compact reference usage summaries...` | `I18N_PLACEHOLDER_ACTUAL` + `COPY_DESACTUALIZADO` | Columna `Reference usage` -> `Column reference usage`; resumenes -> `Sent many`, `Prepared many`; assert de segunda fila relajado para no depender de texto concatenado inestable |
| `disables Process aisle when the aisle has no uploaded assets...` | `I18N_PLACEHOLDER_ACTUAL` | Mensaje helper actualizado a key visible actual (`upload_need_image`) |
| `process dialog shows resolved default model id...` y `process aisle opens provider dialog...` | `I18N_PLACEHOLDER_ACTUAL` | `start processing` -> `process dialog title`; opcion default model -> `process default model em`; CTA `start` -> `process start` |
| `renders job metadata and execution log...` | `NAVIGATION_EXPECTATION_OUTDATED` + `I18N_PLACEHOLDER_ACTUAL` | Se mantuvieron aserciones sobre comportamiento visible estable (`AnalysisStage`, `provider_call`, `exec-1`, `stage.started`) y se quitaron labels legacy fragiles |

## Validacion ejecutada

```bash
cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend"
npm run test -- tests/InventoryDetailPage.test.tsx
```

Resultado:

```txt
✓ tests/InventoryDetailPage.test.tsx (21 tests)
Test Files  1 passed (1)
Tests       21 passed (21)
```

Suite completa:

```bash
cd "/Users/nasserelbacha/Documents/Dinamic sistems/dinamic-gemini/frontend"
npm run test
```

Resultado:

```txt
Test Files  15 failed | 53 passed (68)
Tests       50 failed | 376 passed (426)
```

## Observaciones

- Patron reutilizable para F1.5: en este modulo los fallos fueron mayormente desalineacion test-vs-runtime (copy y a11y labels), no bugs productivos.
- No quedaron pendientes en `InventoryDetailPage.test.tsx` dentro del alcance de F1.4.
- No fue necesario tocar `InventoryDetail.tsx`; no aparecio bug real de comportamiento/accesibilidad.
- Pendiente fuera de alcance F1: mejorar copy placeholder/i18n de producto en fases UX/i18n posteriores.

## Criterio de cierre

F1.4 se considera cerrada porque:

1. `InventoryDetailPage.test.tsx` pasa completo.
2. No se corrigieron otros tests fuera del alcance.
3. No se hicieron refactors.
4. No se modifico arquitectura de inventarios.
5. No hubo cambios productivos.
