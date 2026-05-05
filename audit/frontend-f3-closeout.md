# Cierre F3 — Auditoría conceptual de `useEffect`

**Fecha de cierre:** 2026-05-05  
**Subfases:** F3.0 (auditoría inicial) → F3.5 (consolidación documental).

---

## Resumen ejecutivo

| Campo | Resultado |
|-------|-----------|
| Estado final | **Cerrada** |
| Archivos listados originalmente (F3.0) | 20 |
| Archivos con `useEffect` | 13 |
| Archivos sin `useEffect` | 7 |
| `useEffect` contados en el subconjunto F3 | 21 |
| Subfases ejecutadas | F3.0 a F3.5 |
| Migración a TanStack Query | **No realizada** |
| Cambios de UX | **No intencionales** |
| CI/CD / hooks pre-push / quality gates | **No activados** |

---

## Alcance

La fase **F3** se enfocó en revisar conceptualmente los `useEffect` del frontend en un subconjunto acordado de archivos: lifecycle y cleanup, navegación y URL, bootstrap de autenticación, y gestión de foco/accesibilidad. No incluyó refactors grandes de páginas, migración a TanStack Query, ni cambios de contratos API.

---

## Subfases ejecutadas

### F3.0 — Auditoría inicial

- **Resultado:** Inventario y clasificación conceptual sin cambios productivos.
- **Archivos con efecto:** 13 · **sin efecto:** 7 · **total `useEffect`:** 21 en archivos que sí tenían efectos.
- **Archivos sin `useEffect` detectados:**
  - `frontend/src/pages/AdminAiConfigPage.tsx`
  - `frontend/src/pages/InventoriesList.tsx`
  - `frontend/src/features/reviewQueue/components/QuickReviewDrawer.tsx`
  - `frontend/src/features/analytics/MetricsPage.tsx`
  - `frontend/src/features/inventories/hooks/useAisleProcessingFlow.ts`
  - `frontend/src/components/CreateAisleDialog.tsx`
  - `frontend/src/components/ExecutionLogPanel.tsx`
- **Clasificación general:** La mayoría de los efectos son laterales legítimos: timers/debounce, cleanup de recursos, navegación, sincronización de URL, consumo de `location.state`, foco/accesibilidad, bootstrap de auth.
- **Derivados / `useMemo`:** No se identificaron casos claros de estado derivado que debieran moverse a `useMemo` dentro del subconjunto F3.

---

### F3.1 — Lifecycle, cleanup y hooks utilitarios

**Archivos revisados**

`useDebouncedValue.ts`, `useDebouncedSearchInput.ts`, `CreateInventoryDialog.tsx`, `ManagedImageAssetsDrawer.tsx`, `useEvidenceImageLoad.ts`, `ImageViewer.tsx`

**Archivos modificados**

| Archivo | Cambio |
|---------|--------|
| `CreateInventoryDialog.tsx` | `pendingFilesRef.current = []` tras revocar en `reset`, alineado con cleanup del efecto `[open]`. |
| `useEvidenceImageLoad.ts` | Eliminado segundo `useEffect` de solo unmount; el cleanup del efecto principal es la única fuente de revoke al cambiar spec o desmontar. |

**Efectos mantenidos (sin cambio de intención)**

- Hooks de debounce (timer + cleanup).
- Lifecycle y revoke de previews en `ManagedImageAssetsDrawer`.
- Listener `keydown` (Escape) en `ImageViewer`.
- Cleanup de object URLs en `CreateInventoryDialog`.

**Riesgos corregidos**

- Doble revoke/cleanup redundante en evidencia.
- Ref espejo potencialmente desincronizado tras `reset` del diálogo.

---

### F3.2 — Navegación, URL sync y `location.state`

**Archivos revisados**

`CompareManyRunsPage.tsx`, `CompareRunsPage.tsx`, `PositionDetailPage.tsx`, `AislePositionsPage.tsx`, `ReviewQueuePage.tsx`

**Cambios consolidados**

| Archivo | Cambios relevantes |
|---------|-------------------|
| `CompareManyRunsPage.tsx` | Ref para evitar redirect repetido (inventario no-test); guard si `baseline` en URL ya canónico; **corrección URL de baseline desacoplada de `correctionNoticeRef`** (el ref solo evita repetir el aviso, no bloquea `setSearchParams`). |
| `CompareRunsPage.tsx` | Ref para evitar redirect repetido no-test. |
| `PositionDetailPage.tsx` | Canonicalización de `resultIds` si el state trae array vacío; comentario one-shot + ref `redirected`. |
| `AislePositionsPage.tsx` | No llamar `setSearchParams` para borrar `jobId` si no existe; validación mínima de `openReviewDrawer`; `navigate` con `pathname` + `search` al limpiar state. |
| `ReviewQueuePage.tsx` | Validación de payload `queue`; preservar `location.search` al limpiar state. |

**Riesgos corregidos**

- Doble navegación en guards test-only.
- Escrituras redundantes de URL (`baseline`, `jobId`).
- Pérdida de query string al limpiar `location.state`.
- Payload incompleto al abrir drawers.
- `correctionNoticeRef` bloqueando una corrección válida de baseline (corregido en revisión post–code review).

**Pendiente no bloqueante (F10)**

- Evaluar si payloads inválidos de `location.state.openReviewDrawer` deberían limpiarse con `replace` + `state: {}` para no dejar state basura en history.

---

### F3.3 — AuthProvider

**Archivo revisado:** `frontend/src/features/auth/AuthProvider.tsx`

**Cambios consolidados**

- `bootstrapToken` por ejecución del efecto; cleanup `cancelled` / microtask `cleared` para rama sin token.
- Respuestas de `/auth/me` aplicadas solo si `prev.token === bootstrapToken`; sin pisar token/usuario nuevo.
- `clearStoredSession()` **fuera** del updater de `setState`; bandera `invalidateSession` + clear después del updater (revisión code review).
- `initialized` cubierto en caminos con token / sin token / error.
- Bootstrap permanece en efecto local; comentario de que migrar `GET /auth/me` a TanStack Query implica revisar contrato del provider.

**Riesgos corregidos**

- Carreras por cambio rápido de token y respuestas tardías.
- `setState` tras unmount (guardas + cleanup).
- `initialized` inconsistente en ramas sin token (microtask).
- Efecto secundario (`clearStoredSession`) dentro del updater.

**Pendientes**

- **F6:** Diferenciar error de red temporal vs 401/403 en política fail-closed.
- **F10:** Auth bootstrap con TanStack Query o guards a nivel de ruta.

---

### F3.4 — Focus management y accesibilidad

**Archivo revisado:** `frontend/src/features/results/components/detail/ResultReviewActions.tsx`

**Cambios consolidados**

- Sustitución de `useEffect` por **`useLayoutEffect`** en cuatro efectos: retorno de foco al cerrar editor inline; foco + select al montar `QuantityEditor`, `SkuEditor`, `PositionCodeEditor`.
- Misma lógica de refs y `activeEditor`; sin `autoFocus` duplicado en JSX frente a MUI/TextField controlados.

**Riesgo corregido**

- Foco aplicado después del pintado (flash o orden de lectura menos predecible).

**Pendiente no bloqueante**

- Si `initialValue` cambia sin desmontar el editor, el estado local no se resincroniza (comportamiento previo; fuera de F3).

---

## Archivos modificados en F3 (código productivo)

| Archivo | Subfase | Motivo |
|---------|---------|--------|
| `frontend/src/components/CreateInventoryDialog.tsx` | F3.1 | Sincronizar ref espejo tras `reset` |
| `frontend/src/features/results/hooks/useEvidenceImageLoad.ts` | F3.1 | Eliminar cleanup redundante |
| `frontend/src/pages/analytics/CompareManyRunsPage.tsx` | F3.2 (+ post-review) | Redirect/baseline/notice |
| `frontend/src/pages/analytics/CompareRunsPage.tsx` | F3.2 | Redirect no-test deduplicado |
| `frontend/src/pages/PositionDetailPage.tsx` | F3.2 | `resultIds` + redirect one-shot |
| `frontend/src/pages/AislePositionsPage.tsx` | F3.2 | URL/state/search + payload |
| `frontend/src/pages/ReviewQueuePage.tsx` | F3.2 | Payload + search |
| `frontend/src/features/auth/AuthProvider.tsx` | F3.3 | Bootstrap `/auth/me` robusto |
| `frontend/src/features/results/components/detail/ResultReviewActions.tsx` | F3.4 | `useLayoutEffect` para foco |

---

## Archivos revisados sin cambios de código (muestra F3.1 / alcance)

Entre otros, sin edits en la subfase correspondiente:

- `useDebouncedValue.ts`, `useDebouncedSearchInput.ts` — patrón estándar; deps correctas.
- `ManagedImageAssetsDrawer.tsx`, `ImageViewer.tsx` — efectos considerados correctos; sin cambios obligatorios.

---

## Decisiones técnicas

### `useEffect` mantenidos

Gran parte de los efectos permanecen porque modelan **efectos laterales reales**: temporizadores, suscripciones DOM, navegación, sync de URL, consumo one-shot de router state, bootstrap de sesión, foco.

### `useMemo`

No hubo conversión masiva; en el subconjunto analizado no hubo candidatos claros de “estado derivado en efecto”.

### TanStack Query

No se migró auth ni otros flujos en F3. La deuda principal queda documentada en **AuthProvider** y en posible normalización futura de datos que disparan efectos de URL.

### `useLayoutEffect`

Usado **solo** en F3.4 (`ResultReviewActions`) para alinear foco con el pintado.

---

## Validación

### Estado del repo al cerrar F3.5 (corrida local)

| Comando | Resultado |
|---------|-----------|
| `npm run typecheck` | OK |
| `npm run lint` | OK |
| `npm test -- --run` | Falla: **7 archivos / 17 tests** fallidos (recuento típico; **deuda preexistente**, no atribuible a F3) |

### Por subfase (documentación de trabajo realizado)

| Subfase | Comando / ámbito | Resultado documentado en trabajo |
|---------|------------------|----------------------------------|
| F3.1 | typecheck, lint, tests focalizados (evidence, debounce, ManagedImageAssetsDrawer) | OK en alcance |
| F3.2 | typecheck, lint, tests páginas Compare/Aisle/Review/Position | OK en alcance |
| F3.3 | typecheck, lint, tests `auth` | Fallo conocido `LoginPage` / sesión estructurada — ajeno a F3 |
| F3.4 | typecheck, lint, `ResultReviewActions` tests | OK |

**Nota:** La suite completa del frontend mantiene fallos previos no introducidos por F3. Los comandos **typecheck** y **lint** pasan; las validaciones por archivo/subfase ejecutadas durante el trabajo son las referencia principal para regresión de F3.

---

## Pendientes para fases futuras

### F4 — Components → API / fetch

- Revisar si algún efecto queda como deuda de capa de datos al extraer datos a hooks/API clients (fuera del cierre F3).

### F5 — Complejidad

- Páginas grandes; posible extracción de patrones de URL sync o editores inline cuando se priorice.

### F6 — Manejo de errores

- AuthProvider: distinguir fallos de red vs 401/403 si el producto lo exige.
- Mensajes de error visibles coherentes con política fail-closed.

### F7 — Componentes reutilizables

- Abstraer editores inline si el patrón se repite en más pantallas.

### F10 — React / SOLID / routing avanzado

- Route guards o loaders para navegación post-query.
- Contrato AuthProvider + TanStack Query.
- Limpieza automática de `location.state` inválido.
- Resincronizar `initialValue` en editores si cambia sin remount.

---

## Criterio de cierre

F3 queda **cerrada** porque:

- El subconjunto acordado de `useEffect` fue auditado y las subfases F3.1–F3.4 aplicaron correcciones acotadas donde correspondía.
- Los efectos legítimos quedaron justificados; los problemas concretos identificados fueron corregidos o documentados.
- No se realizó migración a TanStack Query ni refactors masivos no planificados.
- No hay cambios de UX intencionales ni activación de CI/hooks de calidad en esta línea de trabajo.
- Los pendientes están listados para F4/F5/F6/F7/F10.

---

## Recomendación respecto a F4

**Sí:** El frontend puede avanzar a **F4** desde el punto de vista del cierre F3 (auditoría de efectos y parches asociados), asumiendo que la **suite de tests completa** sigue siendo una fuente de deuda conocida y que F4 debe continuar con cambios acotados y validación por área.
