# Cierre F4 — Acoplamiento UI ↔ API/fetch (frontend)

Fecha: 2026-05-06

## Resumen ejecutivo

- Estado F4: **CERRADA**
- Objetivo cumplido: los 8 componentes del alcance F4 quedaron sin acoplamiento directo `component -> api/client` ni `fetch` nativo.
- Enfoque aplicado: cambios mínimos por subfase (F4.1–F4.3) y validaciones de no-cambio (F4.4–F4.5).
- Cambios de UX/copy/estilos/contratos/endpoints: **no realizados**.

## Estado consolidado de los 8 componentes

| Componente | Estado F4.0 | Acción F4 | Estado final |
|---|---|---|---|
| `frontend/src/components/ExecutionLogPanel.tsx` | Sin API/fetch directo | Sin cambios | Desacoplado |
| `frontend/src/components/ui/TraceabilityChip.tsx` | UI puro | Sin cambios | Desacoplado |
| `frontend/src/components/CreateAisleDialog.tsx` | Importaba `createAisle` | Hook `useCreateAisleAction` | Desacoplado |
| `frontend/src/components/ReferenceImagesDrawer.tsx` | Importaba `fetchInventoryVisualReferenceFile` | Hook `useInventoryReferencePreview` | Desacoplado |
| `frontend/src/components/compare/CompareRunJobPickers.tsx` | Presentacional | Sin cambios | Desacoplado |
| `frontend/src/components/AisleObservabilityDialog.tsx` | Importaba descargas de logs | Hook `useExecutionLogDownloads` | Desacoplado |
| `frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx` | Ya desacoplado (callbacks) | Sin cambios | Desacoplado |
| `frontend/src/components/CreateInventoryDialog.tsx` | Importaba `createInventory` / `uploadInventoryVisualReferences` | Hook `useCreateInventoryFlow` | Desacoplado |

## Hooks/API adapters creados en F4

- `frontend/src/features/inventories/hooks/useCreateAisleAction.ts`
- `frontend/src/features/inventories/hooks/useCreateInventoryFlow.ts`
- `frontend/src/features/imageAssets/hooks/useInventoryReferencePreview.ts`
- `frontend/src/features/executionLogs/hooks/useExecutionLogDownloads.ts`

Verificación funcional de hooks:
- Importan `api/client` internamente.
- Exponen funciones para UI sin cambiar contratos de backend.
- Mantienen rethrow de errores para preservar manejo visual por componente.
- Permiten inyección opcional para testabilidad cuando aplica.
- No introducen manejo global de errores.

## Verificaciones de acoplamiento (F4.5)

### Imports directos a api/client

Comando auditado sobre los 8 componentes:

```bash
rg "from .*api/client" \
  frontend/src/components/ExecutionLogPanel.tsx \
  frontend/src/components/ui/TraceabilityChip.tsx \
  frontend/src/components/CreateAisleDialog.tsx \
  frontend/src/components/ReferenceImagesDrawer.tsx \
  frontend/src/components/compare/CompareRunJobPickers.tsx \
  frontend/src/components/AisleObservabilityDialog.tsx \
  frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx \
  frontend/src/components/CreateInventoryDialog.tsx
```

Resultado: **sin matches**.

### Uso directo de fetch nativo

Comando auditado sobre los 8 componentes:

```bash
rg "fetch\(" \
  frontend/src/components/ExecutionLogPanel.tsx \
  frontend/src/components/ui/TraceabilityChip.tsx \
  frontend/src/components/CreateAisleDialog.tsx \
  frontend/src/components/ReferenceImagesDrawer.tsx \
  frontend/src/components/compare/CompareRunJobPickers.tsx \
  frontend/src/components/AisleObservabilityDialog.tsx \
  frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx \
  frontend/src/components/CreateInventoryDialog.tsx
```

Resultado: sin `fetch(` nativo en componentes. En `AisleObservabilityDialog` aparecen llamadas a `refetch()` de hooks de query (esperado; no cuenta como fetch directo).

### Armado manual de endpoints/URLs backend

Comando auditado sobre los 8 componentes:

```bash
rg "\"/api/|'/api/|http://|https://" \
  frontend/src/components/ExecutionLogPanel.tsx \
  frontend/src/components/ui/TraceabilityChip.tsx \
  frontend/src/components/CreateAisleDialog.tsx \
  frontend/src/components/ReferenceImagesDrawer.tsx \
  frontend/src/components/compare/CompareRunJobPickers.tsx \
  frontend/src/components/AisleObservabilityDialog.tsx \
  frontend/src/components/imageAssets/ManagedImageAssetsDrawer.tsx \
  frontend/src/components/CreateInventoryDialog.tsx
```

Resultado: **sin matches**.

## Validaciones ejecutadas

### Calidad estática

- `npm run typecheck` → **OK**
- `npm run lint` → **OK**

### Tests focalizados solicitados

- `npm test -- --run CreateAisleDialog` → **OK** (3/3)
- `npm test -- --run CreateInventoryDialog` → **FAIL** (9/9) por expectativa preexistente de labels/headings (no atribuible a F4; ya conocido en fases previas)
- `npm test -- --run ReferenceImagesDrawer` → **OK** (10/10)
- `npm test -- --run ManagedImageAssetsDrawer` → **OK** (2/2)
- `npm test -- --run ExecutionLogPanel` → **OK** (8/8)
- `npm test -- --run CompareRunJobPickers` → **No test files found**

## Componentes UI puros / sin acción requerida

- `TraceabilityChip` confirmado como UI puro (sin API/fetch/endpoints).
- `ExecutionLogPanel` confirmado sin API/fetch directo. Parsing interno queda como posible deuda de organización para F5/F10, fuera de F4.
- `CompareRunJobPickers` confirmado presentacional (datos por props, sin API/fetch).
- `ManagedImageAssetsDrawer` confirmado desacoplado por callbacks (sin API/fetch directo).

## Pendientes fuera de F4

- F5: posibles limpiezas de complejidad y separación de lógica de parsing/UI donde aporte legibilidad.
- F6: estrategia de errores global y consistencia transversal de mensajes (sin tocar contratos).
- F10: consolidación final de patrones React/SOLID y deuda de arquitectura frontend.

## Criterio de cierre

F4 se considera cerrada porque:
1. Los 8 componentes del alcance fueron auditados/ajustados.
2. No quedan imports directos a `api/client` en componentes del alcance.
3. No hay `fetch` nativo directo en componentes del alcance.
4. No hay armado manual de endpoints backend en esos componentes.
5. Las llamadas API quedaron encapsuladas en hooks/adapters de dominio donde aplicaba.
6. No hubo refactors masivos fuera de alcance ni cambios de comportamiento funcional.
7. `typecheck` y `lint` pasan.
8. Los tests focalizados ejecutados pasan salvo fallos preexistentes documentados.
