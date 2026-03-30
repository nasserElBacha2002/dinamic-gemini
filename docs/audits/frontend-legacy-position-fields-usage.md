# Auditoría: uso real de campos legacy de posición en frontend

**Fecha:** 2026-03-30  
**Alcance:** Consumo de `PositionSummary` / payloads derivados (`ResultDetail`, `ResultSummary`) en `frontend/src` y tests.  
**Método:** búsqueda por símbolos (`rg`) + revisión de mappers.

---

## Resumen

- **`detected_summary_json`:** Usado casi solo en **`positionToResult.ts`** como **fallback histórico** para `source_image_id` cuando los campos tipados vienen vacíos. Baja criticidad para UI actual si el backend siempre envía campos planos.
- **`qty`, `qtySource`, `qtyInferenceReason`, `qtyResolved`, `detected_quantity`, `sku`:** Consumidos vía **`positionToResult`** → tipos **`ResultSummary` / `ResultDetail`** en tablas, drawer, tarjetas y utilidades. **Alta criticidad** — no deprecar en Sprint 1 sin Sprint 2 en API.
- **`internal_code` / `review_display_label`:** No aparecen como acceso directo en componentes; el SKU visible viene de **`position.sku`** ya resuelto por backend.
- **`source_image_id` / `traceability_status`:** Tipados en `PositionSummary` y mapeados en **`positionToResult`** con prioridad a campos planos sobre JSON.

---

## Matriz por campo

| Campo | Archivo(s) | Pantalla / componente | Criticidad | ¿Deprecar ahora? | Reemplazo sugerido (futuro) |
|-------|------------|-------------------------|------------|------------------|-----------------------------|
| `detected_summary_json` | `api/types/responses.ts` (tipo), `features/results/mappers/positionToResult.ts`, `detectedSummary.ts` | Result list → drawer (traceability fallback) | Media | **No** (Sprint 1) | Tras bloque `traceability` en API (Sprint 2), eliminar fallback JSON si backend garantiza campos |
| `detected_quantity` | `positionToResult.ts`, `types.ts`, tests | Resultados, `countOriginLabel` indirecto via `qtySource` | Alta | No | Bloque `quantity.detected` (plan Sprint 2) |
| `qty` | `positionToResult.ts` (`systemQty`, `quantity`), tipos | Drawer, tarjetas, prioridad | Alta | No | `quantity.final` |
| `qtySource` | `positionToResult.ts`, `countOriginLabel.ts`, `types.ts`, tests | Origen del conteo en UI | Alta | No | `quantity.source` |
| `qtyInferenceReason` | Igual que `qtySource` | Tooltip / label inferido | Media–Alta | No | `quantity.inference_reason` |
| `qtyResolved` | `positionToResult.ts`, tests | Visible en modelo resultado | Media | No | `quantity.resolved` |
| `sku` | `AislePositionsPage.tsx`, `ResultsTable.tsx`, `ReviewQueueTable.tsx`, `QuickReviewDrawer.tsx`, `ResultSummaryCard.tsx`, `ResultReviewActions.tsx`, `resultPriority.ts`, `positionToResult.ts` | Lista pasillo, cola, drawer, acciones | **Crítica** | No | `product.sku` (Sprint 2) |
| `internal_code` | — (no uso directo en TSX/TS fuera de JSON opaco) | — | Baja en FE | N/A | Ya cubierto por `sku` API |
| `review_display_label` | — (no grep en src) | — | Baja en FE | N/A | `product.display_label` futuro |
| `source_image_id` | `positionToResult.ts`, `client.ts` (comentario evidencia), tests | Evidencia / imágenes | Alta | No | `traceability.source_image_id` |
| `traceability_status` | `positionToResult.ts` → `mapTraceabilityToVisible` | Badge / estado trazabilidad | Alta | No | `traceability.status` |

---

## Observaciones

1. **`positionToResult.ts`** es el **único** punto que aún lee `detected_summary_json` para producción UI — bien acotado.
2. Los tests **`resultMappers.test.ts`**, **`QuickReviewDrawer.test.tsx`**, **`AislePositionsPage.test.tsx`**, **`ReviewQueuePage.test.tsx`** montan objetos `PositionSummary`; cualquier cambio de contrato requerirá actualizar fixtures.
3. No se encontró uso de **`internal_code`** ni **`review_display_label`** en el árbol `frontend/src` salvo dentro del blob opaco `detected_summary_json` en tipos.

---

## Conclusión Sprint 1

- **No remover** campos legacy del contrato público ni del mapper frontend.
- Tras **Sprint 2** (bloques `product` / `quantity` / `traceability`), migrar **`positionToResult`** gradualmente y solo entonces marcar deprecaciones en tipos.
