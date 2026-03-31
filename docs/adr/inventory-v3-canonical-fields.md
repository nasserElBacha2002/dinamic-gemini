# ADR: Campos canónicos para posiciones e inventario v3

**Estado:** Cerrado — Sprint 1 completado (código y validación alineados con el plan)  
**Fecha:** 2026-03-30  
**Cierre formal:** ver `docs/status/inventory-v3-sprint-1-closeout.md`  
**Relacionado:** `docs/Duplicacion de datos - Plan implementacion.md` (Sprint 1–6), `docs/audits/inventory-v3-data-duplication-audit.md`  
**Código:** `backend/src/application/mappers/position_canonical_view.py`, `backend/src/application/services/position_traceability.py`, `backend/src/api/routes/v3/shared.py` (`position_to_summary`, `_position_summary_response_from_view`)

---

## 1. Propósito

Fijar **una sola semántica de “qué dato manda”** antes de cambiar contratos públicos, CSV o esquema SQL, y centralizar el ensamblado en una capa intermedia (**`PositionCanonicalView`**) que alimente al serializer HTTP actual sin romper compatibilidad.

## 2. Contexto

- Las posiciones persisten `detected_summary_json` (snapshot del pipeline + metadatos de cantidad) y existen filas **`product_records`** generadas en `v3_report_mapper.map_hybrid_report_to_domain`.
- El contrato público (`PositionSummaryResponse`) mezcla columnas de `positions`, proyección desde **`ProductRecord`** y lectura desde **JSON**, lo que duplica cantidad, SKU y trazabilidad.
- El pipeline y la consolidación SKU (`aggregated_from_ids` en `position_sku_consolidation.py`) pueden hacer que **`ProductRecord`** no refleje la cantidad consolidada mostrada en lista/export.

## 3. Problema actual

- **Identidad:** El `sku` público se derivaba con fallback encadenado sobre `detected_summary_json` (`internal_code` → `review_display_label` → …) **incluso cuando existía `primary_product`**, pudiendo divergir de `product_records.sku`.
- **Cantidad:** La verdad operativa está en `ProductRecord` para filas típicas, pero el JSON repite `final_quantity`, `qty_final`, etc.
- **Trazabilidad:** `source_image_id` / `traceability_status` viven en el summary y pueden enriquecerse desde `hybrid_report.json` vía `enrich_position_traceability_from_report` en `application/services/position_traceability.py` (sin depender de helpers privados de rutas).

## 4. Decisiones tomadas (Sprint 1)

| Decisión | Detalle |
|----------|---------|
| **D1** | Cuando exista **`primary_product`** y la fila **no** sea fila consolidada agregada (`aggregated_from_ids` vacío), la **identidad pública de SKU** debe tomarse de **`primary_product.sku`** (incl. sentinela `UNKNOWN`), no de la cascada del summary. |
| **D2** | `detected_summary_json` se trata como **snapshot técnico** (auditoría / replay / consolidación); no como fuente principal del ensamblado cuando D1 aplica. |
| **D3** | Para filas **agregadas** (`aggregated_from_ids` presente y no vacío), la cantidad y el SKU visibles siguen las reglas ya documentadas en código: **`final_quantity`** y datos del summary representativo; **`ProductRecord` puede no alinearse** — decisión pendiente de negocio (ver §9). |
| **D4** | Sin `primary_product`, se mantiene el **fallback legacy** exclusivamente desde summary + reglas de `domain.quantity.resolution`. |
| **D5** | El contrato HTTP **no cambia** en Sprint 1: mismos nombres de campos (`qty`, `qtySource`, `sku`, …). La vista canónica es **interna** hasta Sprint 2+. |
| **D6** | CSV y analytics **no** se modifican en Sprint 1 salvo que reutilicen indirectamente `position_to_summary` (ya delega en la vista canónica). |

## 5. Campos canónicos (negocio)

Cierre **Ticket 1.1** (plan): identidad, cantidad, review, traceability, evidencia y timestamps quedan así cuando aplica la rama “primary + no agregada”.

| Concepto | Fuente canónica | Notas |
|----------|-----------------|-------|
| **SKU / código producto (pantalla)** | `product_records.sku` del **primary** | `select_display_primary_product`; no aplica en rama agregada legacy. Sin fallback silencioso sobre summary si el SKU del record es no vacío (incl. `UNKNOWN`). SKU vacío en record → fallback al summary (ver implementación). |
| **Cantidad “display” / contrato público `qty`** | `ProductRecord` vía `qty_contract_from_product` cuando hay `qty_source`; si no, `detected_quantity` | Equivale hoy a “final display quantity” del plan; renombre explícito a `final_quantity` en API → **Sprint 2** (§9). |
| **Cantidad detectada persistida** | `product_records.detected_quantity` | Alineada con resolución v3.2.2 al ingest. |
| **Cantidad corregida** | `product_records.corrected_quantity` (+ parámetro explícito en `build_position_canonical_view`) | Ver §6. |
| **Procedencia cantidad (rica)** | `product_records.qty_source`, `qty_inference_reason`, etc. | Normalizada a `qtySource` público (`detected`, `inferred`, …, **`consolidated`** cuando aplica). |
| **Estado revisión posición** | `positions.status`, `positions.needs_review` | Flujo revisión / cola; pipeline `count_status` sigue solo en snapshot técnico. |
| **Traceability (foto)** | `detected_summary_json` + enriquecimiento opcional `hybrid_report.json` | `application/services/position_traceability.py`. |
| **Evidencia primaria** | `positions.primary_evidence_id` | `has_evidence` derivado; no confundir con `source_image_id` (foto en reporte). |
| **Timestamps actividad entidad** | `positions.created_at`, `positions.updated_at` | Frescura a nivel posición; `last_activity_at` de inventario/listas es otro agregado (fuera de esta vista). |

## 6. Campos derivados (API)

Construidos en ensamblado — deben **seguir** la vista canónica:

- `qty`, `qtySource`, `qtyInferenceReason`, `qtyResolved`
- `detected_quantity` (alineado a `qty` cuando manda `ProductRecord`; rama legacy puede diferir de `qty` — ver tests de la vista canónica)
- `has_evidence` desde `primary_evidence_id`
- `source_image_id`, `traceability_status`, `source_image_original_filename` (summary + enriquecimiento opcional)
- **`corrected_quantity`** (Sprint 1 — opción A): campo de `PositionCanonicalQuantity`, resuelto en `_effective_corrected_quantity`: si el argumento `corrected_quantity` **no es** `None`, se usa tal cual (incl. `0`); si es `None` y hay `primary_product`, se usa `primary_product.corrected_quantity`; si no hay primary, `None`. No existe hoy forma de forzar “sin corrección” si el primary tiene `corrected_quantity` distinto de `None` sin ajustar el primary. `PositionSummaryResponse` se construye únicamente en `_position_summary_response_from_view`.

## 7. Campos técnicos (snapshot)

Permanecen en **`detected_summary_json`** (no eliminar en Sprint 1):

- `entity_uid`, `entity_type`, `pallet_id`, `internal_code`, `count_status`, …
- Proyección de cantidad al ingest: `qty_final`, `raw_qty`, `qty_parse_status`, `qty_origin_field`, …
- `aggregated_from_ids`, `_audit`

**Implicación API:** el blob sigue expuesto por compatibilidad; el ensamblado principal **no** debe introducir nuevas lecturas “creativas” del JSON cuando D1/D2 aplican.

## 8. Implicancias

- **API (Sprint 1):** Sin cambio de shape; solo orden de fuentes en código.
- **CSV:** Paridad con `position_to_summary` preservada.
- **Persistencia:** Sin migraciones; sin eliminar columnas/JSON.

## 9. Decisiones pendientes

1. **Consolidación SKU:** Si el negocio exige que `product_records` refleje cantidad consolidada o que desaparezcan hijos — hoy el código asume cantidad agregada en summary; documentado en comentarios de `position_to_summary` y consolidación.
2. **Renombre `qty` → `final_quantity`** en API pública: planificado en Sprint 2+; fuera de Sprint 1.
3. **Bloques anidados `product` / `quantity` / `traceability`:** Sprint 2 tickets 2.1–2.3 del plan.

## 10. Relación con el plan por sprints

| Sprint | Tema |
|--------|------|
| **1 (este ADR)** | ADR + auditoría FE + `PositionCanonicalView` + tests paridad |
| **2** | Nuevos bloques en contrato público; alias legacy deprecados |
| **3+** | CSV alineado / slim JSON / analytics sobre tablas |

## 11. Sprint 2 — Contrato enriquecido (implementado)

- **`PositionSummaryResponse`** incluye `product`, `quantity`, `traceability` (Pydantic) poblados **solo** desde `PositionCanonicalView` vía `build_position_canonical_view` + `_position_summary_response_from_view` (sin segundo paso con `primary_product` solo para label).
- **`quantity.final`** = corrección operador si existe, si no `qty` canónico (misma regla que CSV); el campo plano **`qty`** se mantiene como cantidad sistema-resuelta para compatibilidad. En la vista canónica esto es `PositionCanonicalQuantity.final_display_quantity`.
- **`display_label`** y **`barcode`** viven en `PositionCanonicalProduct`; el snapshot técnico y `ProductRecord` se combinan únicamente al construir la vista.
- **`qtySource` / `quantity.source` — `consolidated`:** valor público oficial en Sprint 2 para filas agregadas (`aggregated_from_ids`): indica cantidad consolidada en el summary; alineado con `product_records.qty_source == "consolidated"` cuando aplica la rama de producto.
- Campos planos duplicados marcados **`deprecated=True`** en schema (OpenAPI); sin remoción aún. Cada campo plano tiene una sola declaración en el modelo Pydantic (sin duplicar Field solo para deprecación).
- Detalle y cierre formal Sprint 2: `docs/status/inventory-v3-sprint-2-progress.md`, `docs/status/inventory-v3-sprint-2-closeout.md`.

---

## 12. Sprint 4 — Política final de snapshots técnicos

- **`detected_summary_json`** queda formalmente definido como **snapshot técnico inmutable** para:
  - auditoría
  - debug
  - replay
  - compatibilidad legacy controlada
- **No** es fuente principal del contrato público, del ensamblado operativo ni del CSV estándar cuando existe reemplazo canónico claro (`PositionCanonicalView`, `ProductRecord`, bloques `product` / `quantity` / `traceability`).
- **Uso permitido y esperado**:
  - `technical_snapshot` detail
  - CSV técnico
  - trazabilidad/enriquecimiento técnico cuando aún no existe una persistencia canónica equivalente
  - fallback legacy o transicional explícitamente marcado
- **Uso no permitido como nueva dependencia**:
  - introducir campos operativos nuevos leyendo directo del blob
  - reabrir dependencias frontend sobre el JSON
  - reconstruir el CSV operativo desde el snapshot

## 13. Sprint 4 — Aggregated rows y persistencia

- Las filas con **`aggregated_from_ids`** siguen siendo, por ahora, una **proyección consolidada** generada sobre el snapshot técnico representativo.
- La cantidad visible de una fila agregada puede seguir viniendo del snapshot consolidado (`final_quantity`) y, por diseño actual, **no implica** que exista una fila canónica persistida equivalente en `ProductRecord` con esa misma semántica.
- Cuando hay una fila **no agregada** y existe `primary_product`, los readers nuevos deben preferir la vista canónica / `ProductRecord`.
- Cuando hay una fila **agregada**, si no existe una persistencia canónica inequívoca para esa semántica consolidada, se mantiene el fallback técnico y debe quedar documentado como tal.

## 14. Sprint 4 — `corrected_summary_json`

- La auditoría Sprint 4 encontró **persistencia** de `corrected_summary_json` en `positions`, pero **sin readers funcionales relevantes** en el flujo operativo actual.
- Decisión actual: **deuda técnica a deprecar**, no remover destructivamente todavía.
- Condición para remoción futura:
  - confirmar en producción/consumidores externos que no existe lectura fuera del repositorio SQL
  - mantener trazabilidad de correcciones en `ReviewAction` y en los campos canónicos persistidos antes de cualquier cleanup físico

---

*Aprobación funcional/técnica: según proceso interno del equipo (documentación de ingeniería lista para revisión).*
