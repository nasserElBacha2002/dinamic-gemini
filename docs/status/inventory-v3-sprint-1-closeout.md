# Inventory V3 Sprint 1 Closeout

**Sprint:** 1 — Definir canónicos y desacoplar lógica interna (`docs/Duplicacion de datos - Plan implementacion.md`)  
**Cierre:** 2026-03-30  
**Contrato público:** sin cambio de shape; sin deprecaciones de campos legacy.

---

## 1. Scope completed

| Ticket | Estado | Evidencia principal |
|--------|--------|---------------------|
| **1.1 ADR campos canónicos** | Hecho | `docs/adr/inventory-v3-canonical-fields.md` (cerrado, alineado al código) |
| **1.2 Auditoría frontend** | Hecho | `docs/audits/frontend-legacy-position-fields-usage.md` |
| **1.3 `PositionCanonicalView`** | Hecho | `backend/src/application/mappers/position_canonical_view.py`; ensamblado HTTP en `shared.py` vía `build_position_canonical_view` + `_position_summary_response_from_view` |
| **1.4 Tests paridad** | Hecho | `backend/tests/application/mappers/test_position_canonical_view.py`; `backend/tests/api/test_position_summary_mapping.py` |

**Archivos de implementación clave**

- `backend/src/application/mappers/position_canonical_view.py` — prioridad de fuentes, ramas primary / legacy / agregada.
- `backend/src/application/services/position_traceability.py` — enriquecimiento desde `hybrid_report.json` (sin depender de helpers privados de rutas).
- `backend/src/api/routes/v3/shared.py` — `position_to_summary` delega en la vista canónica; un solo lugar construye `PositionSummaryResponse`.
- `backend/src/api/schemas/position_schemas.py` — `qtySource` incluye `consolidated` (coherente con filas agregadas / producto consolidado).
- CSV / export — sigue usando `position_to_summary` (`inventory_export_rows.py`).

---

## 2. Decisions finalized

- **`ProductRecord`** (primary, rama no agregada): fuente canónica de identidad pública (`sku`, incl. `UNKNOWN`) y de contrato de cantidad cuando hay `qty_source` o `detected_quantity` según reglas existentes.
- **`detected_summary_json`**: snapshot técnico; fallback legacy cuando no hay primary; autoritativo para **cantidad y SKU visibles** solo en rama **`aggregated_from_ids` no vacío** (documentado en ADR §4 D3).
- **`corrected_quantity`**: parte de `PositionCanonicalQuantity`; resolución `_effective_corrected_quantity` (parámetro explícito no-`None` gana; si no, `primary_product.corrected_quantity`).
- **Trazabilidad**: `enrich_position_traceability_from_report` en capa application, compartida por la vista canónica.
- **`qty` público**: sigue siendo la cantidad “display” del contrato actual; renombre / modelo `quantity.final` → **Sprint 2** (plan 2.2).

**Excepciones aceptadas en Sprint 1**

- No se puede forzar “sin corrección” en el summary HTTP si el primary tiene `corrected_quantity != None` sin mutar el agregado pasado al builder (documentado en ADR §6).
- **`position_traceability`** sigue llamando a `api.services` + `runtime.v3_deps` para cargar el reporte (mismo acoplamiento operativo que antes, reubicado).

---

## 3. Remaining gaps (Sprint 2+)

- **Contrato público:** bloques anidados `product` / `quantity` / `traceability` (tickets 2.1–2.3).
- **API:** alias deprecados para campos planos; posible flag `include=technical` para listas.
- **CSV / analytics:** limpieza de columnas duplicadas y migración de lecturas desde `product_records` donde aplique (Sprint 3+ del plan).
- **Negocio consolidación:** alinear o documentar del todo `ProductRecord` vs totales en summary para filas agregadas (deuda explícita ADR §9).

Nada de lo anterior se implementa en Sprint 1 cerrado.

---

## 4. Validation status

**Tests ejecutados en cierre (backend venv):**

- `pytest tests/application/mappers/test_position_canonical_view.py`
- `pytest tests/api/test_position_summary_mapping.py`
- Recomendado antes de merge: `pytest tests/api/test_recomputed_consolidation_e2e.py` (cantidades agregadas / `qtySource`).

**Confianza:** Alta para el alcance Sprint 1 (capa canónica + ensamblado único + trazabilidad desacoplada de `shared`). Riesgo residual acotado a reglas de negocio de consolidación y a clientes que asuman semánticas antiguas sobre `detected_summary_json`.

---

## 5. Recommended next step (inicio Sprint 2)

1. **Ticket 2.1:** Añadir bloque opcional o paralelo `product { id, sku, … }` en `PositionSummaryResponse` / `PositionDetailResponse`, manteniendo `sku` legacy.
2. **Ticket 2.2:** Bloque `quantity { detected, corrected, final, source, … }` alimentado desde `PositionCanonicalView` (sin eliminar aún `qty` / `qtySource` planos).
3. **Frontend:** actualizar `responses.ts` y `positionToResult.ts` tras estabilizar el shape backend; la auditoría Sprint 1 lista los puntos de alto impacto.

Punto de entrada código sugerido: `backend/src/api/schemas/position_schemas.py` → ampliar modelo Pydantic → ` _position_summary_response_from_view` / futuro mapper que serialice desde la vista sin duplicar lógica.

---

*Checkpoint aprobación negocio: proceso interno del equipo.*
