# Generic table sortability — Phase 1 (frontend)

**Fecha:** 2026-05-13  
**Base:** `audit/frontend/generic-table-sortability-audit.md`

## Qué se implementó

- **`DataTableColumn<T>`** ampliado con metadatos opcionales: `sortType`, `sortAccessor`, `sortComparator`, `serverSortKey`, y tipo exportado **`DataTableSortType`**.
- Helper **`sortDataTableRows`** en `frontend/src/components/ui/dataTableSort.ts`: ordenación **en cliente** sobre copia estable, sin mutar el array de entrada; vacíos al final; soporte `string` | `number` | `date` | `boolean`; prioridad `sortComparator` > `sortAccessor`.
- **`DataTable`** sigue sin reordenar filas por sí mismo: solo UI + callbacks (sin cambio de comportamiento visual salvo documentación en cabecera del archivo).
- Exportaciones en `frontend/src/components/ui/index.ts`: `sortDataTableRows`, `DataTableSortType`.
- Tests unitarios: `frontend/tests/dataTableSort.test.ts`.

## Archivos tocados

| Archivo | Cambio |
|---------|--------|
| `frontend/src/components/ui/DataTable.tsx` | Tipos extendidos + comentario |
| `frontend/src/components/ui/dataTableSort.ts` | **Nuevo** helper |
| `frontend/src/components/ui/index.ts` | Reexporta tipos y helper |
| `frontend/src/features/analytics/MetricsPage.tsx` | Estado sort pasillos + `sortDataTableRows` + columnas con accessors |
| `frontend/src/features/analytics/components/MetricsAislesAttentionSection.tsx` | Props `sortBy` / `sortDir` / `onSortChange` → `DataTable` |
| `frontend/src/features/analytics/adapters/metricsViewModel.ts` | Eliminado `sortAisleRowsByAttention` (sustituido por helper genérico) |
| `frontend/src/pages/ClientDetail.tsx` | Tabla inventarios del cliente: sort local con `sortDataTableRows` |
| `frontend/src/pages/InventoriesList.tsx` | Solo metadato `serverSortKey` (= `id`) en columnas ya ordenadas por servidor |
| `frontend/tests/dataTableSort.test.ts` | **Nuevo** |

## Tablas migradas

1. **Métricas — Pasillos con incidencias** (`MetricsAislesAttentionSection` / `MetricsPage`): datos ya cargados en cliente; orden por columna con `sortAccessor` + `sortType`. Orden por defecto: **`pending` descendente** (sustituye el antiguo orden compuesto `sortAisleRowsByAttention`; ver riesgos).
2. **Detalle cliente — inventarios del cliente** (`ClientDetail`): subconjunto acotado filtrado desde hasta 200 ítems; orden local por nombre, estado crudo, pasillos.

## Tablas no migradas (intencional)

| Tabla | Motivo |
|-------|--------|
| `ClientsList`, proveedores en `ClientDetail` | API sin `sort_by` / `sort_dir` — evitar orden engañoso solo en página. |
| `ImportSessionList` | Paginación remota sin sort en backend. |
| `ResultsTable` | Reglas de producto (foto / prioridad) fuera del alcance de esta fase. |
| `InventoriesList` | Ya usa sort servidor; solo se añadió `serverSortKey` documental. |
| `InventoryAislesSection`, `ClientsList`, etc. | No solicitadas en esta fase conservadora. |

## Riesgos que continúan

- **Métricas pasillos:** el orden por defecto ya no es idéntico al antiguo score compuesto “atención”; ahora es **`needs_review_count` desc**. Si se requiere el orden legacy exacto, habría que añadir una columna virtual con `sortComparator` o restaurar un comparador dedicado.
- Listas **paginadas en servidor** sin sort API: siguen sin orden local global hasta fase backend.

## Próxima fase sugerida

- Backend: `sort_by` / `sort_dir` para clientes y proveedores; opcionalmente capture sessions.
- Activar cabeceras sortables en esas listas usando el mismo contrato (`serverSortKey` si difiere del `id`).

## Estado

**GENERIC_TABLE_SORTABILITY_PHASE_1_COMPLETE**
