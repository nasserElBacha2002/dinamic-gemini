# Generic Table Sortability Audit

**Ámbito:** solo frontend (React + TypeScript + MUI + TanStack Query).  
**Fase:** auditoría — sin cambios de código de producción ni de tests.  
**Fecha:** 2026-05-13  

---

## 1. Executive summary

**Estado actual**

- El componente genérico operativo es **`DataTable`** (`frontend/src/components/ui/DataTable.tsx`). Ya expone **`sortable`** por columna, **`TableSortLabel`** de MUI y un modelo **`sort`** controlado por el padre (`sortBy`, `sortDir`, `onSortChange`). **No ordena filas en el cliente**: el comentario del archivo indica explícitamente ordenación **impulsada por el servidor / por el padre**.
- El uso **no es homogéneo**: algunas pantallas pasan `sort` + columnas `sortable`; otras no pasan `sort` (cabeceras sin ordenar aunque se podría); una pantalla (**Métricas — pasillos**) usa paginación + `DataTable` **sin** `sort`; **Resultados de pasillo** delega el criterio de orden en **toggle** fuera de la tabla (`photo` vs `priority`) y la **`ResultsTable`** no usa `sort` del `DataTable`.

**¿La tabla genérica ya “soporta” ordenación?**

- **Sí, a nivel de UI y contrato:** cabeceras clicables cuando `col.sortable && sort` está definido.
- **No a nivel de datos:** no hay `accessor`, `sortType`, comparadores ni ordenación local dentro del componente.

**¿Es consistente entre pantallas?**

- **No.** Mezcla de: (1) servidor (`sort_by` / `sort_dir` en API de inventarios), (2) cliente en el padre (métricas inventario + sesiones de importación), (3) sin orden en UI (clientes, detalle cliente, pasillos en métricas, filas de pasillo en inventario, resultados).

**Dirección recomendada**

- Extender **`DataTableColumn<T>`** con metadatos opcionales (`sortable` por defecto sensato, `sortable: false` para acciones, `sortAccessor` / `sortType` / `sortComparator`, `serverSortKey`) y **una capa opcional** en el padre o un hook `useDataTableSort` que:
  - para listas **paginadas en servidor**, traduzca `col.id` → parámetros API y resetee página;
  - para listas **en memoria / página completa**, aplique ordenación estable en cliente usando **valores crudos**, no nodos React.
- Unificar **Resultados** (hoy toggle + API `sort_by` en página) con el mismo modelo mental: o columnas `DataTable` alineadas con el criterio activo, o documentar que esa pantalla es un caso especial.

**Tag de estado final:** **`SORTABILITY_READY_WITH_RISKS`**

---

## 2. Generic table architecture

| Aspecto | Detalle |
|--------|---------|
| **Componente principal** | `frontend/src/components/ui/DataTable.tsx` |
| **Exportaciones** | `frontend/src/components/ui/index.ts` — `DataTable`, tipos `DataTableColumn`, `DataTableSortModel`, `DataTablePaginationModel`, `DataTableSortDirection` |
| **Soporte visual** | `Table`, `TableHead`, `TableSortLabel` (MUI), `TablePagination` |
| **Genérico tipado** | `DataTable<T>`, `DataTableColumn<T>` con `cell: (row: T) => ReactNode` |
| **Declaración de columnas** | Objeto por columna: `id`, `label`, opcional `align`, `width`, **`sortable?: boolean`**, **`cell`** |
| **Valores crudos** | No hay campo `accessor` en el tipo; el padre solo puede ordenar si conoce `T` y duplica lógica o usa helpers (p. ej. `sortInventoryRows` en `features/analytics/adapters/metricsViewModel.ts`) |
| **Filas** | `rows.map` → `col.cell(row)` por celda |
| **Paginación** | Opcional `pagination` — índice de página **1-based** alineado con APIs v3 |
| **Clic en fila** | `onRowClick` + exclusión de botones/enlaces/menús (`clickTargetShouldSkipRowNavigation`) |

**Limitación explícita en código:** sin ordenación oculta de `rows` dentro de `DataTable`; el estado y la semántica dependen del contenedor.

---

## 3. Current sorting behavior

| Aspecto | Comportamiento |
|--------|----------------|
| **UI de orden** | `TableSortLabel` solo si **`sort` está definido** y **`col.sortable === true`**. |
| **Orden en componente** | Ninguno sobre el array `rows`. |
| **Controlado / no controlado** | **Controlado:** `sort.sortBy`, `sort.sortDir`, `sort.onSortChange`. |
| **Dónde vive el estado** | En la página o en hooks (`useState` en `InventoriesList`, `MetricsPage`, etc.). No en URL salvo lo que cada pantalla añada en el futuro. |
| **Servidor vs cliente** | **Inventarios (lista):** `sort_by` / `sort_dir` en `useInventoriesList` → `getInventories` / canonicalización en `queryParamCanonicalization.ts`. **Métricas (rendimiento por inventario):** orden en cliente (`sortInventoryRows`) y luego paginación sobre el array ordenado. **Sesiones de importación:** orden **solo** por `created_at` en `useMemo` en `ImportSessionList`; el clic en cabecera solo alterna dirección (`onSortChange` ignora `sortBy`). **Clientes / detalle cliente / pasillos inventario / resultados:** sin modelo `sort` en `DataTable` o sin columnas sortables. |

---

## 4. Table usage inventory

| Pantalla / flujo | Ruta del componente | Fuente de datos / hook | Paginación | Orden actual | Riesgo | Notas |
|------------------|---------------------|-------------------------|------------|---------------|--------|--------|
| Lista de inventarios | `pages/InventoriesList.tsx` | `useInventoriesList` (`sort_by`, `sort_dir`, `page`, `page_size`) | **Remota** (API) | Servidor; columnas marcadas `sortable` + `sort` | **LOW** | Contrato v3 ya alineado con `DataTable`. `processing_mode` explícitamente `sortable: false`. |
| Lista de clientes | `pages/ClientsList.tsx` | `useClients` | **Remota** (solo `page`, `page_size`; API sin `sort_by`) | Sin orden en cabecera; búsqueda local en página actual | **MEDIUM** | Ordenar solo la página actual sería engañoso hasta que el backend soporte `sort_by`. |
| Detalle cliente — proveedores | `pages/ClientDetail.tsx` | `useClientSuppliers` | Lista paginada en API (`page`, `page_size`) | Sin `sort` en `DataTable` | **MEDIUM** | Mismo tema: orden global requiere API. |
| Detalle cliente — inventarios del cliente | `pages/ClientDetail.tsx` | `useInventoriesList` (200 ítems, filtro cliente) | Ventana grande fija | Sin `sort` en tabla | **LOW** | Conjunto acotado a un cliente; orden **cliente** sobre esos ítems sería razonable si se define `sortAccessor`. |
| Pasillos del inventario | `features/inventories/components/InventoryAislesSection.tsx` | Props (`filteredTableRows`); datos desde página inventario | Sin paginación en `DataTable` | Sin `sort`; filtro texto cliente | **MEDIUM** | Muchas columnas con **render** complejo (badges, menú de acciones). Orden por valor mostrado vs crudo requiere decisión por columna. |
| Métricas — rendimiento por inventario | `features/analytics/components/MetricsInventoryPerformanceSection.tsx` + `MetricsPage.tsx` | `getAnalyticsInventoryPerformance` + `sortInventoryRows` | **Cliente** (slice después de ordenar) | Cliente + UI `sort` | **LOW** | Ya hay comparador centralizado por `sortBy` string. Columna `name` explícitamente `sortable: false`. |
| Métricas — pasillos con incidencias | `features/analytics/components/MetricsAislesAttentionSection.tsx` | `MetricsPage` (`sortAisleRowsByAttention` + paginación) | **Cliente** | Orden fijo **sin** cabeceras clicables | **LOW** | Añadir `sort` requiere definir criterios por columna (hoy el orden es “atención”, no el id de columna). |
| Sesiones de importación | `features/ingestionSessions/components/ImportSessionList.tsx` | `useCaptureSessionsList` (`page`, `page_size` hasta 100) | **Remota** (una página grande) | Cliente solo por `created_at` | **MEDIUM** / **HIGH** si crece el listado | Si `total_items > page_size`, el orden por fecha **solo** en la página cargada es incorrecto frente al total; haría falta **`sort_by` en backend** o cargar todo. |
| Resultados del pasillo | `features/results/components/ResultsTable.tsx` + `AisleResultsTableSection.tsx` | `AislePositionsPage` + API posiciones (`sort_by` según modo foto/prioridad) | **Remota** | Orden vía **toggle** + query API, no vía `DataTable` | **HIGH** para mapear a columnas | Columnas numéricas/fechas/badge; orden “prioridad” es **derivado** (`deriveResultPriority`). |
| (Tests / integración) | `frontend/tests/dataTable*.tsx` | Mock | — | Cobertura de `onSortChange` | **LOW** | Referencia de contrato actual. |

---

## 5. Column-level findings (resumen representativo)

*Convención de estrategia:* `CLIENT_*` = orden en cliente sobre filas disponibles; `SERVER_SORT_PARAM` = parámetro API; `NOT_SORTABLE_*` = acción o control; `NOT_RECOMMENDED` = engañoso o sin valor semántico claro.

| Pantalla | Columna (id) | Origen del valor | ¿Sortable hoy? | ¿Recomendado sortable? | Estrategia | Notas |
|----------|--------------|------------------|----------------|-------------------------|------------|--------|
| Inventarios | `name` | `inv.name` | Sí (UI + API) | Sí | `SERVER_SORT_PARAM` (`id` alineado con `sort_by`) | Enlace; no usar texto renderizado como clave en API. |
| Inventarios | `status` | `inv.status` (+ etiqueta i18n) | Sí | Sí | `SERVER_SORT_PARAM` | Ordenar por **código de estado**, no por etiqueta traducida. |
| Inventarios | `processing_mode` | `inv.processing_mode` | No (`sortable: false`) | Opcional | `SERVER_SORT_PARAM` o dejar falso | Producto ya lo desactivó. |
| Inventarios | fechas / contadores | campos numéricos / ISO | Sí | Sí | `SERVER_SORT_PARAM` | Asegurar tipos numéricos y fechas en backend. |
| Clientes | `name`, `status`, fechas | campos `Client` | No | Sí (si hay API) | `SERVER_SORT_PARAM` | Backend `list_clients` hoy **sin** `sort_by`/`sort_dir` → dependencia. |
| Clientes | `actions` | botón “Ver” | No | **No** | `NOT_SORTABLE_ACTION_COLUMN` | |
| Detalle cliente — proveedores | varias | `ClientSupplier` | No | Sí con API | `SERVER_SORT_PARAM` | Misma brecha de API que clientes. |
| Detalle cliente — inventarios | varias | `InventoryListItem` | No | Sí | `CLIENT_STRING` / `CLIENT_NUMBER` / `CLIENT_DATE` | Lista filtrada acotada. |
| Pasillos inventario | `code` | `row.presentation.code` | No | Sí | `CLIENT_STRING` | |
| Pasillos inventario | `aisle_status` | etiqueta + semántica | No | Sí con cuidado | `CLIENT_CUSTOM_COMPARATOR` o clave estable | Orden por **enum/código** subyacente, no por copy. |
| Pasillos inventario | `assets`, `results_found`, etc. | numéricos en `presentation` | No | Sí | `CLIENT_NUMBER` | |
| Pasillos inventario | `actions` | `RowActionMenu` | No | **No** | `NOT_SORTABLE_ACTION_COLUMN` | |
| Métricas inventario | `name` | nombre inventario | No (`sortable: false`) | Opcional | `CLIENT_STRING` | Hoy deshabilitado quizá para no competir con el router link; se puede reabrir con cuidado UX. |
| Métricas inventario | métricas numéricas / % | campos en `InventoryPerformanceRow` | Sí | Sí | `CLIENT_NUMBER` (vía `sortInventoryRows`) | Ya mapeados en `metricsViewModel`. |
| Métricas pasillos | `aisle`, `inventory`, contadores | `AisleIssueRow` | No | Sí | `CLIENT_NUMBER` / `CLIENT_STRING` | Sustituir o complementar `sortAisleRowsByAttention` con orden por columna. |
| Sesiones importación | `created_at` | ISO | UI “sí” pero solo toggla dir | Sí | `CLIENT_DATE` en página actual **o** `SERVER_SORT_PARAM` | **Recomendado servidor** si la lista paginada crece. |
| Sesiones importación | `open` / `id` | acciones / enlace | No / parcial | **No** en `open` | `NOT_SORTABLE_ACTION_COLUMN` | `id` como enlace: no ordenar por UI de botón. |
| Resultados | `priority` | derivado `deriveResultPriority` | No en `DataTable` | Sí en modo “priority” | `CLIENT_CUSTOM_COMPARATOR` o servidor si existe | Ya hay orden API en página para una de las modalidades. |
| Resultados | `sku`, `qty`, `confidence`, `updated` | campos + formato | No | Sí | `CLIENT_NUMBER` / `CLIENT_DATE` / `CLIENT_STRING` según modo | Debe alinearse con **photo_sequence** vs prioridad para no contradecir el toggle. |

---

## 6. Recommended implementation strategy (fases)

**Fase 0 — Contrato y documentación**

- Documentar en `DataTable.tsx` que `col.id` en columnas `sortable` **debe** coincidir con la clave que el padre envía a la API **o** con la clave del comparador cliente (tabla de equivalencia en un solo sitio).
- Añadir al tipo (futuro) algo alineado al proyecto, por ejemplo:

```ts
type SortType = 'string' | 'number' | 'date' | 'boolean';

type GenericTableColumn<T> = {
  id: string;
  label: string;
  accessor?: keyof T | ((row: T) => unknown);
  render?: (row: T) => React.ReactNode;  // en el código actual: `cell`
  sortable?: boolean;
  sortType?: SortType;
  sortAccessor?: (row: T) => unknown;
  sortComparator?: (a: T, b: T) => number;
  serverSortKey?: string; // si difiere de `id`
};
```

(adaptar nombres: hoy el proyecto usa `cell`, no `render`.)

**Fase 1 — Infra sin romper pantallas**

- Valores por defecto: **`sortable: false`** para columnas de acciones; **`sortable: true`** solo donde el padre pueda cumplir (evita cabeceras activas sin efecto).
- Hook opcional `useServerTableSort({ initialSortBy, initialSortDir, onQueryChange })` que resetee página y actualice query keys.

**Fase 2 — Pantallas de bajo riesgo**

- `ClientDetail` tablas pequeñas: orden cliente con `sortAccessor`.
- `MetricsAislesAttentionSection`: añadir `sort` + comparadores por columna (reutilizar patrón de `sortInventoryRows`).

**Fase 3 — Servidor**

- `GET /api/v3/clients` y `GET .../suppliers`: añadir `sort_by` / `sort_dir` (cambio **backend**) y cablear `InventoriesList`-like en listas de clientes.
- `capture-sessions`: si el volumen crece, **`sort_by` en API** + query keys; hasta entonces documentar límite de `page_size: 100`.

**Fase 4 — Resultados**

- Decisión de producto: ¿columnas `DataTable` reflejan el modo **photo** vs **priority** (cabeceras deshabilitadas o orden distinto), o se mantiene el toggle y solo se añaden columnas sortables compatibles con el modo activo?

**Evitar:** duplicar lógica de comparación en cada página; ordenar por string renderizado (p. ej. porcentajes formateados); usar `label` i18n como `sort_by` en API.

---

## 7. Server-side sorting considerations

| Endpoint / lista | Params actuales (relevantes) | ¿Orden en API? | Frontend |
|------------------|----------------------------|----------------|----------|
| `GET /api/v3/inventories` | `page`, `page_size`, **`sort_by`**, **`sort_dir`**, `search`, … | **Sí** | `inventoriesApi` + `canonicalizeInventoriesListQuery`; query keys incluyen sort. |
| `GET /api/v3/clients` | `page`, `page_size` | **No** | `clientsApi` sin sort; listar orden global requiere **backend**. |
| `GET .../clients/{id}/suppliers` | `page`, `page_size` | **No** | Misma limitación. |
| `GET .../inventories/{id}/capture-sessions` | `page`, `page_size`, filtros fecha/estado | **No** `sort_by` | Orden local en `ImportSessionList` solo sobre ítems cargados. |
| Posiciones / resultados de pasillo | `sort_by`, `sort_dir` (v3 positions / jobs) | **Sí** | `AislePositionsPage` alterna criterios; no pasa por `DataTable`. |
| Analytics (resumen, rendimiento, etc.) | params de fechas / alcance | **Sin** sort genérico en contrato | Orden **solo** en cliente (`metricsViewModel`). |

**Regla:** si la tabla está **paginada en el servidor** y solo se recibe una ventana de filas, **ordenar solo en cliente** la página actual **no** representa el orden global → **engañoso** o debe documentarse como “orden en esta página”.

---

## 8. Backward compatibility risks

- **Tests** (`dataTable.test.tsx`, integración menú): asumen cabeceras y callbacks; al añadir orden por defecto hay que no romper “solo etiqueta” cuando `sort` es `undefined`.
- **Etiquetas i18n:** deben seguir siendo solo UI; las claves API y comparadores usan **campos crudos** o `serverSortKey`.
- **Fechas / números formateados:** `formatDate`, `formatPct`, `toFixed` en celdas — el orden debe usar **ISO / number**, no el string mostrado.
- **Columnas derivadas** (prioridad en resultados, badges compuestos): requieren `sortAccessor` o `sortComparator` explícito.
- **Acciones / menús:** riesgo de habilitar `sortable` por defecto en columnas `actions` → confusión UX; conviene **opt-out** explícito o convención “id termina en `_actions`”.
- **TanStack Query:** al añadir `sort_by` a nuevas listas, incluir sort en **queryKey** (como ya hace inventarios).
- **URL / estado:** hoy casi ninguna tabla persiste sort en la URL; si se añade, impacto en compartir enlaces y en “reset filtros”.

---

## 9. Testing strategy (futura implementación; no escribir tests en esta fase)

- **Unitarios:** comparador genérico por `sortType` (string locale, número, fecha ISO, boolean); empates estables.
- **Componente `DataTable`:** clic en `TableSortLabel` → `onSortChange` con `sortBy`/`sortDir`; columnas sin `sortable` no disparan; sin `sort` no hay `TableSortLabel` en columnas marcadas sortables (comportamiento actual o nuevo según decisión).
- **Columnas de acción:** cabecera no clic o no ordena.
- **Integración inventarios:** cambio de columna actualiza query (mock API) y `page === 1`.
- **Métricas:** orden cambia el orden de filas en la primera página para un `sortBy` conocido.
- **Regresión:** snapshots o tests existentes de listas que hoy no ordenan.

---

## 10. Recommended next phase

1. **Implementar primero en el tipo + `DataTable`** documentación y campos opcionales (`sortAccessor`, `sortType`, `serverSortKey`, `sortable` por defecto conservador) **sin** activar sort global en todas las columnas.
2. **Empezar con orden cliente** en tablas de **conjunto acotado** (`ClientDetail` inventarios, `InventoryAislesSection` si el producto confirma criterios).
3. **Preparar hooks** tipo `useInventoriesList` para **clientes y proveedores** cuando exista contrato API (`sort_by` / `sort_dir`).
4. **Diferir** orden “completo” en **sesiones de importación** hasta **sort en backend** o hasta acotar volumen.
5. **Coordinar** **resultados del pasillo** con UX: alinear toggle existente con cabeceras o mantener un solo modo de orden explícito.

**Dependencias backend:** `sort_by`/`sort_dir` en **clientes** y **proveedores**; opcionalmente en **lista de capture sessions** si se exige orden global con paginación.

---

## Referencias rápidas de archivos

| Archivo | Rol |
|---------|-----|
| `frontend/src/components/ui/DataTable.tsx` | Tabla genérica, `TableSortLabel`, tipos de columna y sort |
| `frontend/src/pages/InventoriesList.tsx` | Referencia de integración **servidor** + `sort` |
| `frontend/src/features/analytics/adapters/metricsViewModel.ts` | `sortInventoryRows` — patrón **cliente** centralizado |
| `frontend/src/features/ingestionSessions/components/ImportSessionList.tsx` | Orden cliente parcial + UI sort |
| `frontend/src/features/results/components/ResultsTable.tsx` | Tabla sin `sort`; orden controlado fuera |
| `frontend/src/api/queryParamCanonicalization.ts` | `sort_by` / `sort_dir` para inventarios |
| `backend/src/api/routes/v3/inventories.py` | Query `sort_by`, `sort_dir` |
| `backend/src/api/routes/v3/clients.py` | Lista sin sort |
