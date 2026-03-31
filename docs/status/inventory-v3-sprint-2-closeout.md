# Inventory V3 Sprint 2 Closeout

**Sprint:** 2 — Contrato público enriquecido (`product` / `quantity` / `traceability`) sin romper compatibilidad  
**Plan:** `docs/Duplicacion de datos - Plan implementacion.md` (tickets 2.1–2.5)  
**Referencias:** `docs/adr/inventory-v3-canonical-fields.md` §11, `docs/status/inventory-v3-sprint-1-closeout.md`, `docs/status/inventory-v3-sprint-2-progress.md`  
**Cierre:** 2026-03-30  

---

## 1. Scope verified

| Ticket | Estado | Evidencia |
|--------|--------|-----------|
| **2.1 — Bloque `product`** | **Completo** | `PositionProductBlock` en `position_schemas.py`; mismo `PositionSummaryResponse` en lista y detalle (`PositionDetailResponse.position`); ensamblado desde `PositionCanonicalProduct` (`display_label`, `barcode`, `public_sku`, `identity_source`). Campo plano `sku` deprecado en OpenAPI. Tests: `test_position_summary_sprint2_contract.py`, `test_position_canonical_view.py`. |
| **2.2 — Bloque `quantity`** | **Completo** | `PositionQuantityBlock`; datos desde vista canónica + `final_display_quantity`; alias planos deprecados. **`quantity.final`** = corrección operador si existe, si no cantidad sistema resuelta (`qty` canónico), no la fórmula simplificada del plan “corrected ?? detected” cuando `detected` ≠ contrato sistema — alineado a ADR y CSV `final_quantity`. `consolidated` como fuente pública estable (filas agregadas / registro consolidado). |
| **2.3 — Bloque `traceability`** | **Completo** | `PositionTraceabilityBlock` con `status`, `source_image_id`, `source_image_original_filename`, `primary_evidence_id`, `has_evidence`; semántica documentada (foto reporte vs evidencia crop); alias planos deprecados. |
| **2.4 — Identidad canónica** | **Completo** | `primary_product.sku` manda en rama no agregada; `UNKNOWN` estable; `internal_code` solo vía snapshot técnico / fallback summary, no como identidad pública principal; `review_display_label` → display auxiliar en `_canonical_display_label`. |
| **2.5 — Deprecaciones** | **Completo con deferencia explícita** | Campos planos duplicados marcados `deprecated=True` en Pydantic (OpenAPI). **No** se deprecó aún `detected_summary_json` en el endpoint de lista: el plan lo enlaza al **Sprint 3** (ticket 3.1 — slim list / flag técnico); coherente con el alcance acordado “sin remoción / sin cambio CSV” del progreso Sprint 2. |

---

## 2. Implementation summary

### Backend

- **Schemas:** `backend/src/api/schemas/position_schemas.py` — bloques anidados; literales `qty`/`traceability` alineados a contrato; sin campos duplicados en `PositionSummaryResponse` (verificación por modelo + test).
- **Ensamblado:** `backend/src/api/routes/v3/shared.py` — `position_to_summary` → `build_position_canonical_view` → `_position_summary_response_from_view`; un solo sitio de construcción.
- **Vista canónica:** `backend/src/application/mappers/position_canonical_view.py` — `display_label`, `barcode`, `final_display_quantity` en la capa canónica; sin lógica dispersa extra en el serializer salvo mapeo 1:1 vista → respuesta.

### Frontend

- **Tipos:** `frontend/src/api/types/responses.ts` — bloques opcionales para payloads antiguos; `PositionQtySourceV322` incluye `consolidated`; traceability con `ApiTraceabilityStatus | string`.
- **Mapper:** `frontend/src/features/results/mappers/positionToResult.ts` — prioridad explícita: bloques anidados → alias plano → inferencia histórica donde aplica.

### Alias legacy (conservados)

- Planos: `sku`, `qty`, `qtySource`, `qtyInferenceReason`, `qtyResolved`, `detected_quantity`, `corrected_quantity`, `source_image_id`, `traceability_status`, `has_evidence`, `primary_evidence_id`, `source_image_original_filename`, más `detected_summary_json` sin deprecación de schema en lista (Sprint 3).

---

## 3. Validation summary

### Backend (pytest)

- `tests/api/test_position_summary_sprint2_contract.py` — primary, legacy, agregado, UNKNOWN implícito, `quantity.final` vs `qty`, traceability enrichment, unicidad de campos del modelo, coexistencia bloques + planos.
- `tests/application/mappers/test_position_canonical_view.py` — paridad Sprint 1 + campos UX en vista canónica.
- `tests/api/test_position_summary_mapping.py` — regresión ensamblado y casos consolidados / agregados.

### Frontend (vitest)

- `frontend/tests/resultMappers.test.ts` — `consolidated`, traceability, fallbacks; **añadido:** preferencia de bloques Sprint 2 cuando chocan con planos.

### Nivel de confianza

**Alto** para el alcance Sprint 2: contrato enriquecido, compatibilidad legacy, una capa canónica coherente con Sprint 1, y tests que cubren los caminos críticos listados en el plan. Residual: clientes que ignoren OpenAPI deprecations; reducción de JSON técnico en lista queda fuera de alcance.

---

## 4. Open items for Sprint 3 (intencional)

- **Lista / snapshot:** ticket 3.1 del plan — `detected_summary_json` solo en detalle o bajo `include_technical` (u opción equivalente).
- **CSV / export:** alinear columnas y lecturas (plan Sprint 3).
- **Tipos FE:** endurecer obligatoriedad de bloques cuando el backend garantice 100 % de respuestas nuevas en todos los entornos.
- **Deuda negocio:** consolidación SKU / `ProductRecord` vs totales en summary (ADR §9) — seguimiento producto.

---

## 5. Closure decision

**Sprint 2 queda formalmente cerrado** para los tickets **2.1–2.4** y para **2.5** en el sentido de deprecaciones OpenAPI de campos planos duplicados y documentación alineada. La única viñeta del texto del plan 2.5 que apunta a **`detected_summary_json` en list** se trató como **alcance Sprint 3** (ticket 3.1), no como bloqueador de este cierre, porque el mismo plan la desarrolla en la siguiente fase y el equipo ya había acotado Sprint 2 sin slim de lista.

**Justificación breve:** el código y los tests verificados coinciden con el ADR y el documento de progreso; no hay duplicación de campos en el schema backend ni claves duplicadas en el mapper; list y detail comparten `PositionSummaryResponse`; la semántica de `consolidated` y de `quantity.final` está cerrada y documentada.

---

*Aprobación funcional: proceso interno del equipo.*
