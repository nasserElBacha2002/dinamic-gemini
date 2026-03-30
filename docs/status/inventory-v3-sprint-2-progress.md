# Inventory V3 Sprint 2 — Progreso (contrato público enriquecido)

**Plan:** `docs/Duplicacion de datos - Plan implementacion.md` (tickets 2.1–2.5)  
**Fecha:** 2026-03-30  
**Compatibilidad:** campos planos legacy conservados; sin remoción; sin cambio CSV/DB/analytics.

---

## 1. Implementado

| Ticket | Contenido |
|--------|-----------|
| **2.1** | Bloque `product` (`PositionProductBlock`): `id`, `sku`, `display_label`, `barcode`, `identity_source` |
| **2.2** | Bloque `quantity` (`PositionQuantityBlock`): `detected`, `corrected`, `final`, `source`, `inference_reason`, `resolved` |
| **2.3** | Bloque `traceability` (`PositionTraceabilityBlock`): `status`, `source_image_id`, `source_image_original_filename`, `primary_evidence_id`, `has_evidence` |
| **2.4** | Identidad alineada a `PositionCanonicalView` + `public_display_label` / `public_barcode`; `UNKNOWN` sin sustitución por summary |
| **2.5** | Campos planos marcados `deprecated=True` en Pydantic (OpenAPI) con descripción de reemplazo |

**Ensamblado:** `backend/src/api/routes/v3/shared.py` — `_position_summary_response_from_view` construye bloques desde la vista canónica + `primary_product` (label) + helpers `public_display_label`, `public_barcode`, `quantity_final_display` en `position_canonical_view.py`.

**Semántica clave**

- **`quantity.final`:** `corrected_quantity` si no es `None`, si no `qty` canónico (misma regla que CSV `final_quantity`). El **`qty` plano legacy** sigue siendo la cantidad **resuelta por el sistema** (sin aplicar corrección como override), para no romper clientes existentes.
- **`detected_quantity` plano / `quantity.detected`:** cantidad detectada resuelta en el contrato v3.2.2 (alineada con primary cuando aplica).
- **`display_label`:** `ProductRecord.description` si no vacío; si no, `review_display_label` del snapshot.
- **`barcode`:** solo `position_barcode` del snapshot si existe.

---

## 2. Archivos principales

| Área | Archivo |
|------|---------|
| Schemas | `backend/src/api/schemas/position_schemas.py` |
| Mapper | `backend/src/api/routes/v3/shared.py` |
| Canónico | `backend/src/application/mappers/position_canonical_view.py` (`public_display_label`, `public_barcode`, `quantity_final_display`) |
| Tests API | `backend/tests/api/test_position_summary_sprint2_contract.py` |
| FE tipos | `frontend/src/api/types/responses.ts` |
| FE mapper | `frontend/src/features/results/mappers/positionToResult.ts` (prefiere bloques cuando existen) |
| FE tipos resultado | `frontend/src/features/results/types.ts` (`consolidated` en `qtySource`) |

---

## 3. Legacy / deprecado (sin remoción)

Marcados con `Field(deprecated=True)` en `PositionSummaryResponse` donde aplica:

| Legacy | Reemplazo documentado |
|--------|------------------------|
| `sku` | `product.sku` |
| `detected_quantity` | `quantity.detected` |
| `corrected_quantity` | `quantity.corrected` |
| `qty` | `quantity.final` (UX); nota: `qty` sigue siendo qty sistema |
| `qtySource` | `quantity.source` |
| `qtyInferenceReason` | `quantity.inference_reason` |
| `qtyResolved` | `quantity.resolved` |
| `source_image_id` | `traceability.source_image_id` |
| `traceability_status` | `traceability.status` |
| `has_evidence` | `traceability.has_evidence` |
| `primary_evidence_id` | `traceability.primary_evidence_id` |
| `source_image_original_filename` | `traceability.source_image_original_filename` |

---

## 4. Pendiente (Sprint 3+)

- Quitar o acotar `detected_summary_json` en **list** (flag `?include=technical` u otro).
- CSV alineado explícitamente a bloques o a columnas slim.
- Analytics sobre tablas / menos `JSON_VALUE` en summary.
- Endurecer tipos TS para exigir `product`/`quantity`/`traceability` cuando el backend garantice 100 % de respuestas nuevas.

---

## 5. Impacto frontend

- Los tipos permiten `product` / `quantity` / `traceability` opcionales para payloads antiguos; el mapper **prefiere** bloques cuando vienen del backend.
- Pantallas que solo usan campos planos **siguen funcionando**; migración gradual a bloques sin breaking change inmediato.

---

*Ver también:* `docs/adr/inventory-v3-canonical-fields.md`, `docs/status/inventory-v3-sprint-1-closeout.md`.
