# Panel unificado de Analítica

Documentación funcional y técnica del módulo **Analítica** (`/analitica`) en Dinamic Inventory v3.

## 1. Overview

Analítica consolida en un solo panel:

- Métricas de **posiciones** (revisión, calidad, tiempos agregados).
- Métricas de **corridas** (observabilidad de jobs LLM).
- **Costos** desde snapshots `llm_cost_snapshot`.
- **Comparación** de corridas (embebida y ruta standalone).
- **Drilldowns** por inventario y pasillo.

No sustituye pantallas operativas (posiciones, cola de revisión). Sirve para supervisión, auditoría y enlaces compartibles.

## 2. Routes and redirects

| Ruta | Comportamiento |
|------|----------------|
| `/analitica` | Panel unificado; pestaña por defecto `resumen`. |
| `/metrics` | Redirige a `/analitica?tab=calidad` (legacy). |
| `/observabilidad` | Redirige a `/analitica?tab=proveedores` (legacy). |
| `/inventories/:id/analytics/compare-many` | Comparación avanzada standalone (se conserva). |
| `/inventories/:id/analytics/compare` | Redirige a compare-many. |

La navegación lateral expone un único ítem **Analítica** (`nav.analytics`).

## 3. URL tabs and filters

### Pestañas (`tab`)

Valores en español en la URL:

| URL | Pestaña interna |
|-----|-----------------|
| `resumen` | Resumen |
| `calidad` | Calidad |
| `tiempos` | Tiempos |
| `proveedores` | Proveedores |
| `inventarios` | Inventarios |
| `pasillos` | Pasillos |
| `comparacion` | Comparación |
| `costos` | Costos |

Tab inválido o ausente → `resumen`.

### Filtros (snake_case en URL)

| Parámetro | Campo UI |
|-----------|----------|
| `date_from` | Desde |
| `date_to` | Hasta |
| `inventory_id` | Inventario |
| `aisle_id` | Pasillo |
| `client_id` | Cliente |
| `client_supplier_id` | Proveedor del cliente |
| `provider_name` | Proveedor LLM |
| `model_name` | Modelo |

**Ejemplo compartible:**

```txt
/analitica?tab=pasillos&date_from=2026-01-01&date_to=2026-01-31&inventory_id=inv-1&aisle_id=a-1
```

Reglas:

- Fechas por defecto (últimos 30 días) no se escriben en la URL.
- Cadenas vacías o solo espacios se omiten.
- `aisle_id` sin `inventory_id` se ignora (pasillos dependen de inventario).
- Fechas inválidas o `date_from > date_to` → rango por defecto; la URL se normaliza.
- Parámetros desconocidos se conservan al aplicar o resetear filtros.
- **Actualizar** filtros: `replace: false` (historial del navegador).
- **Limpiar filtros**: quita parámetros de filtro; mantiene `tab`.

Implementación: `frontend/src/constants/analyticsFilters.ts`, `analyticsTabs.ts`, `AnalyticsDashboardPage.tsx`.

## 4. Data sources

| Fuente | Hook / API | Uso principal |
|--------|------------|---------------|
| Analytics positions | `useAnalyticsDashboard` → `/api/v3/analytics/*` | Resumen, calidad, inventarios, pasillos, tendencias |
| Observability | `useObservabilityMetrics` | Proveedores, tiempos por corrida, volumen |
| Cost summary | `useAnalyticsCostSummary` → `GET /api/v3/analytics/cost-summary` | Costos, KPIs LLM, gráficos de costo |
| Aisle jobs | `useAisleJobsList` | Solo al abrir drilldown de pasillo (máx. 20) |
| Compare-many | `CompareManyRunsWorkspace` | Solo pestaña Comparación o ruta standalone |

Los tres endpoints principales se cargan en paralelo al montar el panel; el cambio de pestaña **no** cambia las claves de query si los filtros aplicados no cambian (caché TanStack Query).

## 5. Metric grains

| Grano | Descripción |
|-------|-------------|
| **Posiciones / acciones de revisión** | Tasas de aceptación, corrección, trazabilidad; tablas de inventario/pasillo. |
| **Jobs / corridas** | Observabilidad: duración, proveedor, modelo, estado. |
| **Compare (slice seleccionado)** | Métricas de las corridas elegidas en compare-many; no son globales del inventario. |

Las etiquetas de KPI indican el grano cuando aplica (`grainLabel` en tarjetas).

## 6. Cost semantics

- Los costos provienen de **`llm_cost_snapshot`** agregado en backend (`cost-summary`).
- **No** se estiman costos faltantes en frontend.
- Estados de captura: `exact`, `estimated`, `partial`, `unavailable` (según backend).
- **Costo por unidad contada** solo se muestra cuando el backend devuelve valor seguro; si no → **No disponible**.
- **Costo por unidad proveedor/modelo** no se calcula globalmente en frontend (`PROVIDER_MODEL_UNIT_COST_NOT_AVAILABLE`).
- Jobs sin snapshot aparecen en advertencias; no se cuentan como cero.

## 7. Quantity semantics

- Cantidad contada puede reflejar estado operativo actual según advertencia backend (`COUNTED_QUANTITY_*`).
- En **comparación**, la cantidad es por corrida seleccionada.
- **Delta de cantidad** en benchmark es **neutral** (no “mejor/peor”).
- Posiciones consolidadas en compare: delta neutral.

## 8. Review / correction semantics

- `needs_review_count` = **requieren revisión**, no correcciones completadas.
- Drilldown de pasillo incluye texto aclaratorio (`notCorrectionsHelper`).
- Tasas de corrección manual en analytics positions ≠ conteo de ítems en cola de revisión.

## 9. Provider/model semantics

- El panel **compara** comportamiento por proveedor/modelo (volumen, tiempos, costos agregados).
- **No** hay “mejor proveedor”, ranking de calidad ni recomendación automática.
- Gráfico “Corridas por proveedor/modelo” describe volumen de corridas, no confiabilidad.

## 10. Drilldowns

- Drawer lateral (responsive: ancho completo en móvil).
- Alcance = filtros y fechas aplicados en Analítica (`scopeCaption`).
- Advertencias de costo en drilldown son del **alcance analítico**, no específicas de la entidad.
- Inventario: KPIs de costo, pasillos con mayor contribución, enlaces a posiciones/compare.
- Pasillo: KPIs, tabla de últimas 20 corridas (`useAisleJobsList` con `enabled` solo si hay contexto y drawer abierto).
- Jobs **no** se consultan con el drawer cerrado ni en modo inventario.

## 11. Run comparison

- **Embebida**: pestaña Comparación con inventario de prueba (`processing_mode: test`).
- **Standalone**: `/inventories/:id/analytics/compare-many` con query opcionales `aisleId`, `jobIds`, `baseline`.
- Benchmark Phase 7: resumen ejecutivo, tarjetas, deltas KPI, gráficos, advertencias de contexto, resumen de diferencias.
- Costos summables: `exact`, `estimated`, `partial` únicamente.
- Moneda mixta en resumen ejecutivo → total no disponible (no sumar divisas).

## 12. Warnings and partial data

- `AnalyticsDataQualitySummary`: fallos parciales por endpoint, snapshots ausentes, códigos de warning de costo.
- `hasPartialFailure`: banner informativo si solo falla costos y posiciones/observabilidad cargaron.
- Fallo **simultáneo** de analytics + observabilidad → `ErrorAlert` global con reintento.
- Fallo de costos **no** oculta métricas de posiciones en Resumen.
- `hasMixedLoadedData`: un origen cargó y el otro quedó vacío sin error.

## 13. Known limitations

- Filtros `client_id` / `client_supplier_id` pueden aplicar solo a observabilidad/costos según backend.
- Fechas por defecto no aparecen en URL (enlaces “default” no incluyen `date_from`/`date_to`).
- Compare-many no se ejecuta hasta abrir pestaña Comparación o la ruta standalone.
- Validación de `aisle_id` frente al inventario seleccionado es de UI (sin fetch global de pasillos).
- Inventarios `production` redirigen fuera de compare embebido/standalone según reglas existentes.

## 14. Testing checklist

Comandos habituales (desde `frontend/`):

```bash
npm run typecheck
npm run lint
npm test -- analyticsNavigation analyticsFilters appRoutes navConfig
npm test -- AnalyticsDashboardPage AnalyticsCostsTab AnalyticsCharts
npm test -- AnalyticsDrilldownDrawer AnalyticsCompareTab
npm test -- CompareBenchmarkViewModel CompareManyRunsPage CompareManyRunsWorkspace
npm test -- LegacyAnalyticsRedirects
npm run build
```

Cobertura mínima esperada:

- [ ] URL tabs: default, inválido, cambio preservando filtros
- [ ] URL filters: init, apply, reset, back/forward, aisle sin inventario, fechas inválidas
- [ ] Redirects `/metrics`, `/observabilidad`
- [ ] Nav único Analítica
- [ ] Drilldown jobs solo con drawer pasillo abierto
- [ ] Cost warnings y unit cost no disponible
- [ ] Compare neutro en cantidades; moneda mixta
- [ ] Fallos parciales visibles

---

## Phase 9 audit snapshot (read-only baseline)

**Status:** `READY_WITH_MINOR_RISKS`

**Potential performance risks:** Tres endpoints siempre al montar el panel (aceptable con caché); compare-many solo en pestaña activa; jobs solo en drilldown pasillo.

**Potential semantic risks:** Bajo control vía advertencias y copy; no computar valores faltantes en frontend.

**Backend follow-up:** Ninguno bloqueante identificado en revisión estática de contratos v3; optimizaciones de agregación en `cost-summary` quedan como mejora opcional (`BACKEND_FOLLOWUP_REQUIRED` solo si profiling en producción lo exige).
