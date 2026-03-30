# ADR: Campos canónicos para posiciones e inventario v3

**Estado:** Aceptado (Sprint 1 — implementación en curso)  
**Fecha:** 2026-03-30  
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

Origen preferido cuando aplica:

| Concepto | Fuente canónica | Notas |
|----------|-----------------|-------|
| **SKU / código producto (pantalla)** | `product_records.sku` del **primary** | `select_display_primary_product`; no aplica en rama agregada legacy. |
| **Cantidad detectada persistida** | `product_records.detected_quantity` | Alineada con resolución v3.2.2 al ingest. |
| **Cantidad corregida** | `product_records.corrected_quantity` | Review / correcciones. |
| **Procedencia cantidad (rica)** | `product_records.qty_source`, `qty_inference_reason`, `raw_qty_json`, `qty_parse_status` | Normalizada a contrato público simplificado (`qtySource`, …) en el mapper. |
| **Estado revisión posición** | `positions.status`, `positions.needs_review` | |
| **Evidencia primaria** | `positions.primary_evidence_id` | `has_evidence` derivado. |

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

---

*Aprobación funcional/técnica: pendiente según proceso interno del equipo.*
