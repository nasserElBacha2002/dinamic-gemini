# Inventory V3 Sprint 3 — Progreso

**Plan:** `docs/Duplicacion de datos - Plan implementacion.md` (tickets 3.1–3.5)  
**Fecha:** 2026-03-31  
**Base:** `docs/adr/inventory-v3-canonical-fields.md`, `docs/status/inventory-v3-sprint-1-closeout.md`, `docs/status/inventory-v3-sprint-2-progress.md`, `docs/status/inventory-v3-sprint-2-closeout.md`  
**Compatibilidad:** sin migraciones DB; sin cambios analytics SQL; aliases legacy top-level aún presentes.  

---

## 1. Tickets implementados

| Ticket | Estado | Resumen |
|--------|--------|---------|
| **3.1 — Acotar `detected_summary_json` en list** | **Implementado** | El list endpoint **ya no expone el blob técnico por defecto**; `position_to_summary(..., include_technical_snapshot=False)` deja `detected_summary_json = null/omitido según serialización`. Para clientes internos/transicionales existe `?include_technical=true` en list. |
| **3.2 — `technical_snapshot` explícito en detail** | **Implementado** | `PositionDetailResponse` agrega `technical_snapshot` con shape técnico claro (`entity_uid`, `entity_type`, `internal_code`, `review_display_label`, `position_barcode`, `pallet_id`, `count_status`, `raw_qty`, `qty_parse_status`, `qty_origin_field`, `aggregated_from_ids`, `audit`). `position.detected_summary_json` queda como **legacy** y marcado deprecated en schema. |
| **3.3 — CSV estándar alineado al contrato canónico** | **Implementado** | El export estándar usa columnas operativas alineadas al contrato público: `product_sku`, `product_display_label`, `barcode`, `detected_quantity`, `corrected_quantity`, `final_quantity`, `qty_source`, `traceability_status`, etc. La construcción sale de `PositionCanonicalView`, no del serializer HTTP ni de lecturas ad hoc del snapshot. |
| **3.4 — CSV técnico opcional** | **Implementado** | Nuevo modo `technical=true` en `/api/v3/inventories/{inventory_id}/export`, con CSV separado para campos del snapshot (`internal_code`, `review_display_label`, `position_barcode`, `raw_qty`, `qty_parse_status`, `qty_origin_field`, `entity_uid`, `entity_type`, `_audit`, ...). |
| **3.5 — Paridad API vs CSV** | **Implementado (focalizado)** | Tests validan que el CSV estándar represente `product`, `quantity` y `traceability` del contrato operativo; también hay tests del serializer para list sin snapshot y detail con `technical_snapshot`. |

---

## 2. Cambios en list endpoint

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions`
  ahora acepta `include_technical=false` por defecto.
- Sin ese flag, el list deja de depender normalmente de `detected_summary_json`.
- Con `include_technical=true`, el blob legacy puede seguir saliendo temporalmente para debugging/compatibilidad.

**Decisión:** no se removió todavía el campo del schema compartido porque list/detail siguen reutilizando `PositionSummaryResponse`; en cambio se desactiva su población por defecto en list para evitar romper el detalle y mantener transición controlada. La separación explícita de schemas queda documentada como deuda intencional para Sprint 4, no como refactor incompleto de Sprint 3.

---

## 3. Cambios en detail endpoint

- `GET /api/v3/inventories/{inventory_id}/aisles/{aisle_id}/positions/{position_id}`
  agrega `technical_snapshot` top-level.
- `position.detected_summary_json` queda como campo legacy/deprecated de schema, pero el backend ya no lo puebla en las superficies consumidas por frontend (`list`, `detail`, `review_queue`).
- El frontend detail ahora puede leer:
  - contrato operativo: `position.product`, `position.quantity`, `position.traceability`
  - snapshot técnico: `technical_snapshot`

---

## 4. `technical_snapshot`

### Shape actual

```json
{
  "technical_snapshot": {
    "entity_uid": "job_x_E1",
    "entity_type": "PALLET",
    "internal_code": "SKU-123",
    "review_display_label": "Shelf tag",
    "position_barcode": "123456789",
    "pallet_id": "P-01",
    "count_status": "COUNTED",
    "raw_qty": "4x",
    "qty_parse_status": "invalid",
    "qty_origin_field": "product_label_quantity",
    "aggregated_from_ids": ["pos-a", "pos-b"],
    "audit": {
      "explicit_quantity_missing": true
    }
  }
}
```

### Regla

- El bloque sale del snapshot técnico real (`detected_summary_json`) vía `PositionCanonicalView.technical_snapshot`.
- No duplica semántica canónica ya expuesta en `product`, `quantity`, `traceability`.
- `source_image_id` / `primary_evidence_id` siguen viviendo en `traceability`, no en `technical_snapshot`.
- `audit` queda explícitamente documentado como **blob técnico flexible**: útil para debugging/auditoría, pero todavía no tratado como contrato público estable por clave.

---

## 5. CSV estándar

### Encabezados operativos

- `inventory_id`
- `inventory_name`
- `aisle_id`
- `aisle_code`
- `aisle_sequence`
- `position_id`
- `position_status`
- `needs_review`
- `position_code`
- `product_sku`
- `product_display_label`
- `barcode`
- `detected_quantity`
- `corrected_quantity`
- `final_quantity`
- `qty_source`
- `qty_inference_reason`
- `traceability_status`
- `source_image_id`
- `primary_evidence_id`
- `updated_at`

### Notas

- `position_code` y `aisle_sequence` se mantienen como columnas operativas auxiliares por compatibilidad razonable.
- `position_code` sigue siendo útil para operadores porque representa la referencia humana estable de ubicación/slot (`pallet_id` → `position_barcode` → `entity_uid` → `position.id`) y además es la base del orden natural del export dentro del pasillo.
- `aisle_sequence` se mantiene como ayuda operativa/exportable para preservar el orden determinista por pasillo ya usado en el CSV, sin obligar a consumidores a reconstruirlo externamente.
- `internal_code` y `_audit` salen del CSV estándar; quedan en el CSV técnico.

---

## 6. CSV técnico

- Endpoint: mismo export con `?technical=true`
- Archivo: `inventory_<id>_technical.csv`
- Objetivo: auditabilidad / debugging sin contaminar el CSV operativo

Campos principales:

- `internal_code`
- `review_display_label`
- `position_barcode`
- `pallet_id`
- `entity_uid`
- `entity_type`
- `count_status`
- `raw_qty`
- `qty_parse_status`
- `qty_origin_field`
- `aggregated_from_ids`
- `audit_json`

---

## 7. Frontend

- La lista ya no necesita `detected_summary_json` para el flujo normal.
- En detail, `positionToResult.ts` prioriza el contrato nuevo y usa `technical_snapshot` para metadata técnica (`entity_uid`).
- El frontend ya no depende de `position.detected_summary_json`; el fallback legacy fue retirado para que el front no reciba ni consuma más ese blob.

---

## 8. Tests / validación

**Backend**

- `tests/application/use_cases/test_export_inventory_results.py`
- `tests/api/test_position_summary_mapping.py`
- `tests/api/test_position_summary_sprint2_contract.py`

**Frontend**

- `frontend/tests/resultMappers.test.ts`

**Cobertura agregada en Sprint 3**

- list serializer sin snapshot técnico por defecto
- extracción de `technical_snapshot`
- CSV estándar alineado al contrato operativo
- CSV técnico separado
- frontend detail con preferencia por `technical_snapshot` para metadata técnica

---

## 9. Pendiente para Sprint 4

- Remoción final o estrechamiento más agresivo de aliases legacy top-level.
- Decidir si `PositionSummaryResponse` se divide formalmente entre list/detail en schema público.
- Decidir si el campo deprecated `detected_summary_json` se elimina por completo del contrato backend o se conserva solo para clientes internos no-frontend.
- Cleanup adicional de consumers API HTTP del export si se requiere migración externa de encabezados.
- Analytics SQL y persistencia slim del snapshot.
- Reglas de negocio más profundas para filas consolidadas/agregadas si producto define cambios.

---

## 10. Estado

**Sprint 3 quedó iniciado con los tickets 3.1–3.5 encaminados/implementados** en esta iteración, con foco en separar contrato operativo vs snapshot técnico sin cambios destructivos de DB o frontend.
