# Inventory V3 Sprint 4 Progress

**Plan:** `docs/Duplicacion de datos - Plan implementacion.md` (tickets 4.1–4.5)  
**Fecha:** 2026-03-31  
**Base:** `docs/adr/inventory-v3-canonical-fields.md`, `docs/audits/inventory-v3-data-duplication-audit.md`, `docs/audits/frontend-legacy-position-fields-usage.md`, `docs/status/inventory-v3-sprint-1-closeout.md`, `docs/status/inventory-v3-sprint-2-closeout.md`, `docs/status/inventory-v3-sprint-3-progress.md`

---

## 1. What was verified

### `detected_summary_json`

- **Serializers / API**
  - `backend/src/api/schemas/position_schemas.py`
  - `backend/src/api/routes/v3/shared.py`
  - `backend/src/api/routes/v3/positions.py`
- **Application / services**
  - `backend/src/application/mappers/position_canonical_view.py`
  - `backend/src/application/services/position_traceability.py`
  - `backend/src/application/services/position_sku_consolidation.py`
  - `backend/src/application/utils/review_queue_derived.py`
  - `backend/src/application/use_cases/update_product_sku.py`
- **Persistence / repositories**
  - `backend/src/infrastructure/repositories/sql_position_repository.py`
  - `backend/src/infrastructure/pipeline/v3_report_mapper.py`
- **Analytics**
  - `backend/src/infrastructure/repositories/sql_analytics_repository.py`
  - `backend/src/infrastructure/repositories/memory_analytics_repository.py`
- **Exports**
  - `backend/src/application/mappers/inventory_export_rows.py` (solo técnico / compatibilidad operativa puntual)
- **Frontend**
  - tipado residual en `frontend/src/api/types/responses.ts`
  - ya no hay dependencia funcional activa del mapper principal sobre ese blob

### `corrected_summary_json`

- Existe en:
  - `backend/src/domain/positions/entities.py`
  - `backend/src/infrastructure/repositories/sql_position_repository.py`
  - `backend/src/infrastructure/pipeline/v3_report_mapper.py`
  - schema SQL `positions.corrected_summary_json`
- **Readers funcionales encontrados:** ninguno relevante fuera de parseo/persistencia de repositorio.

### Aggregated / consolidated rows

- La proyección consolidada actual sigue en:
  - `backend/src/application/services/position_sku_consolidation.py`
  - `backend/src/application/mappers/position_canonical_view.py`
  - `backend/src/application/use_cases/list_aisle_positions.py`
  - `backend/src/application/use_cases/export_inventory_results.py`
- Regla observada:
  - `aggregated_from_ids` se marca en el snapshot representativo
  - `final_quantity` consolidada vive hoy en esa proyección técnica
  - `ProductRecord` no garantiza reflejar exactamente la misma semántica en todos los casos agregados

### Legacy top-level fields consumidos

- Siguen con consumo real en frontend, principalmente vía `positionToResult` y modelos derivados:
  - `sku`
  - `detected_quantity`
  - `corrected_quantity`
  - `qty`
  - `qtySource`
  - `qtyInferenceReason`
  - `qtyResolved`
  - `source_image_id`
  - `traceability_status`
  - `has_evidence`
  - `primary_evidence_id`
  - `source_image_original_filename`
- `detected_summary_json` quedó como tipado legacy, no dependencia funcional activa del flujo principal frontend.

---

## 2. Decisions implemented

### Política final de `detected_summary_json`

- Se documentó como **snapshot técnico / audit / replay**, no como fuente principal del contrato público.
- Se alinearon docstrings y schema descriptions para dejar explícito que:
  - list no lo debe poblar por defecto
  - detail debe preferir `technical_snapshot`
  - bloques canónicos y aliases públicos no deben reconstruirse desde el blob salvo fallback legacy explícito
- Se endureció la regla de gobernanza:
  - todo reader nuevo debe justificar explícitamente por qué consulta el snapshot técnico
  - si existe reemplazo canónico claro, el snapshot no debe consultarse
  - las únicas excepciones aceptadas sin nueva persistencia canónica son audit/debug/replay, compatibilidad transitoria explícita y filas aggregated

### Readers / analytics migrados

- **Memory analytics** dejó de clasificar buckets críticos exclusivamente desde el JSON cuando existe `ProductRecord`.
- La clasificación de:
  - `invalid_traceability`
  - `quantity_zero`
  ahora prefiere `PositionCanonicalView` + `primary_product` cuando existe.
- `MemoryAnalyticsRepository` ahora precalcula y reutiliza `primary_by_position` por conjunto de posiciones relevante, evitando resolver repetidamente `list_by_position(...)` + `select_display_primary_product(...)` dentro de loops.
- Para filas **agregadas**, se mantiene fallback técnico intencional porque todavía no hay una persistencia canónica inequívoca para esa semántica consolidada.
- **SQL analytics** redujo dependencia del blob para `quantity_zero`:
  - prioriza `product_records.corrected_quantity` / `detected_quantity` en filas no agregadas
  - conserva fallback al snapshot para agregadas/legacy
  - alcance real de esta iteración: bucketing de analytics (`quantity_zero`) en `sql_analytics_repository.py`; no implica migración completa del repositorio SQL fuera del snapshot

### `corrected_summary_json`

- Decisión adoptada: **Opción B**.
- Se documenta como deuda técnica persistida sin readers operativos relevantes detectados.
- No se elimina todavía del schema/persistencia porque faltaría verificar consumidores externos y estrategia de cleanup físico.

| Aspecto | Estado |
|--------|--------|
| **Writers** | `backend/src/infrastructure/pipeline/v3_report_mapper.py` lo inicializa en `None`; `backend/src/infrastructure/repositories/sql_position_repository.py` persiste el valor presente en `Position.corrected_summary_json`. |
| **Readers** | `backend/src/infrastructure/repositories/sql_position_repository.py` lo hidrata al leer filas; no se detectaron readers operativos relevantes adicionales. |
| **Persistencia** | Columna `positions.corrected_summary_json`, parseo/hidratación en entidad `Position`. |
| **Estado actual** | Blob legacy persistido, visible en repositorio/entidad, sin rol canónico ni consumo funcional importante identificado. |
| **Condición de remoción** | Verificar consumidores externos reales fuera del repositorio SQL y asegurar que la trazabilidad de correcciones ya quede cubierta por `ReviewAction` + campos canónicos persistidos. |

### Aggregated rows

- Decisión adoptada para Sprint 4:
  - mantener la semántica actual como **proyección consolidada virtual/técnica**
  - no inventar una persistencia nueva de negocio en `ProductRecord`
  - readers nuevos deben preferir canónico solo en filas no agregadas con reemplazo claro

---

## 3. Remaining technical debt

- `traceability_status` sigue sin una persistencia canónica equivalente fuera del snapshot; analytics SQL aún depende del blob para esa parte.
- `corrected_summary_json` sigue físicamente en DB y repositorio.
- `PositionSummaryResponse` continúa compartido entre list/detail.
- Los aliases top-level legacy siguen presentes porque frontend y posibles clientes externos todavía los consumen.
- La política definitiva de persistencia canónica para filas agregadas sigue pendiente de decisión funcional más profunda.

---

## 4. Readiness for legacy cleanup

### Estado actual

- **Frontend** ya está listo para vivir sin `detected_summary_json`.
- **Frontend** todavía consume masivamente aliases top-level para SKU/cantidad/trazabilidad visible.
- **Backend** ya tiene suficientes bloques canónicos para sostener la migración final, pero falta reducir consumers activos.

### Blockers concretos

- migrar consumo frontend restante desde aliases top-level a:
  - `product`
  - `quantity`
  - `traceability`
- decidir si list/detail se separan formalmente en schemas públicos
- cerrar política de persistencia canónica para filas agregadas
- verificar si existe algún consumidor externo real de `corrected_summary_json`

### Readiness

- **Alta** para endurecer deprecaciones y seguir retirando dependencias al snapshot.
- **Media** para remoción final de aliases top-level.
- **Baja** para remoción física de blobs persistidos sin una verificación adicional de consumers externos / estrategia de migración.
