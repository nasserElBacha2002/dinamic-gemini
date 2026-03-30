# **Sprint 1 — Definir canónicos y desacoplar la lógica interna**

## **Objetivo**

Antes de cambiar contratos o DB, dejar resuelto **qué dato manda** y encapsular esa decisión en backend.

## **Ticket 1.1 — Crear ADR de campos canónicos**

### **Objetivo**

Documentar la fuente canónica para:

* identidad de producto  
* cantidad final  
* review state  
* traceability  
* evidence linkage  
* activity timestamps

### **Archivos probables**

* `docs/adr/inventory-v3-canonical-fields.md`

### **Decisiones mínimas a dejar cerradas**

* `ProductRecord` es fuente canónica de negocio para identidad/cantidad cuando exista.  
* `detected_summary_json` pasa a considerarse snapshot técnico.  
* `qty` actual equivale a “final display quantity” y deberá migrar a `final_quantity`.  
* `sku` público no debe seguir resolviéndose por fallback silencioso si existe `primary_product`.

### **Criterios de aceptación**

* Documento creado y versionado.  
* Aprobación funcional/técnica interna.  
* Lista explícita de campos “canónicos”, “derivados” y “técnicos”.

---

## **Ticket 1.2 — Auditar uso real en frontend de campos legacy**

### **Objetivo**

Saber qué pantallas dependen todavía de:

* `detected_summary_json`  
* `detected_quantity`  
* `qty`  
* `qtySource`  
* `qtyInferenceReason`  
* `qtyResolved`  
* `internal_code`  
* `review_display_label`

### **Archivos probables**

* `frontend/src/api/types/responses.ts`  
* pantallas de inventory/aisle/results/review/drawer  
* hooks/query mappers relacionados

### **Criterios de aceptación**

* Tabla de uso por campo.  
* Lista de campos que pueden deprecarse sin romper UI.  
* Lista de campos que requieren transición.

---

## **Ticket 1.3 — Crear `PositionCanonicalView` en backend**

### **Objetivo**

Introducir una capa intermedia que arme una vista canónica de posición antes del serializer público.

### **Archivos probables**

* `backend/src/api/routes/v3/shared.py`  
* o nueva carpeta tipo:  
  * `backend/src/application/read_models/`  
  * `backend/src/application/mappers/position_canonical_view.py`

### **Contenido esperado**

Un assembler que construya:

* `product`  
* `quantity`  
* `traceability`  
* `review`  
* `technical_snapshot_ref` opcional

### **Reglas**

* preferir `primary_product`  
* usar `detected_summary_json` solo como fallback legacy  
* no mezclar datos sin marcar prioridad

### **Criterios de aceptación**

* existe una estructura canónica reusable  
* `position_to_summary` deja de armar datos desde múltiples lugares “inline”  
* tests unitarios para casos:  
  * con `primary_product`  
  * sin `primary_product`  
  * aggregated row  
  * legacy summary-only

---

## **Ticket 1.4 — Testear paridad de cantidad e identidad**

### **Objetivo**

Evitar divergencias invisibles entre:

* `product_records`  
* `detected_summary_json`  
* response actual

### **Archivos probables**

* tests de mappers/serializers  
* tests de posición list/detail

### **Criterios de aceptación**

* tests cubren:  
  * `sku`  
  * `detected_quantity`  
  * `corrected_quantity`  
  * `qty/final`  
  * `qtySource`  
  * `source_image_id`  
* se detecta explícitamente si el summary técnico diverge del dato canónico

---

# **Sprint 2 — Limpiar contrato público y resolver identidad/cantidad**

## **Objetivo**

Empezar a corregir la API pública sin romper compatibilidad.

## **Ticket 2.1 — Introducir nuevo bloque `product` en PositionSummary/Detail**

### **Objetivo**

Separar identidad pública de los campos legacy.

### **Propuesta de shape**

* `product.id`  
* `product.sku`  
* `product.display_label`  
* `product.barcode`  
* `product.identity_source` opcional

### **Archivos probables**

* `backend/src/api/schemas/position_schemas.py`  
* `backend/src/api/routes/v3/shared.py`  
* `frontend/src/api/types/responses.ts`

### **Criterios de aceptación**

* nuevos campos presentes en list y detail  
* `sku` legacy sigue existiendo por compatibilidad  
* frontend puede empezar a consumir `product.sku`

---

## **Ticket 2.2 — Introducir nuevo bloque `quantity`**

### **Objetivo**

Dejar un modelo claro y explícito de cantidades.

### **Propuesta**

* `quantity.detected`  
* `quantity.corrected`  
* `quantity.final`  
* `quantity.source`  
* `quantity.inference_reason`  
* `quantity.resolved`

### **Regla**

`quantity.final = corrected ?? detected`

### **Archivos probables**

* `position_schemas.py`  
* `shared.py`  
* tests de serializers  
* frontend types

### **Criterios de aceptación**

* todos los datos salen desde la vista canónica  
* `qty`, `qtySource`, `qtyInferenceReason`, `qtyResolved` siguen temporalmente como alias deprecated  
* `detected_quantity` queda explícitamente documentado como “resolved detected quantity”

---

## **Ticket 2.3 — Introducir nuevo bloque `traceability`**

### **Objetivo**

Separar trazabilidad del resto del payload y dejar claro qué representa cada cosa.

### **Propuesta**

* `traceability.status`  
* `traceability.source_image_id`  
* `traceability.source_image_original_filename`  
* `traceability.primary_evidence_id`  
* `traceability.has_evidence`

### **Criterios de aceptación**

* el bloque existe en list y detail  
* `source_image_id`, `traceability_status`, `has_evidence`, `primary_evidence_id` legacy siguen saliendo por compatibilidad  
* naming y semántica documentadas

---

## **Ticket 2.4 — Definir identidad pública canónica**

### **Objetivo**

Eliminar ambigüedad entre:

* `sku`  
* `internal_code`  
* `review_display_label`  
* `barcode`

### **Reglas esperadas**

* si existe `primary_product.sku`, esa es la identidad pública  
* `internal_code` no se usa como campo público principal  
* `review_display_label` pasa a ser auxiliar/display  
* `barcode` es opcional, no identidad principal por defecto

### **Criterios de aceptación**

* `product.sku` no depende de cascada opaca si existe `primary_product`  
* tests cubren fallbacks legacy  
* documentación actualizada

---

## **Ticket 2.5 — Deprecar campos legacy del contrato actual**

### **Objetivo**

Marcar como deprecated:

* `sku`  
* `qty`  
* `qtySource`  
* `qtyInferenceReason`  
* `qtyResolved`  
* `detected_quantity` si sigue redundante  
* `detected_summary_json` en list endpoint

### **Criterios de aceptación**

* schemas/documentación marcan deprecación  
* no se rompe compatibilidad todavía  
* changelog interno listo para frontend

---

# **Sprint 3 — Reencuadrar snapshot técnico y alinear CSV**

## **Objetivo**

Separar definitivamente el bloque técnico del contrato operativo y limpiar el export.

## **Ticket 3.1 — Mover `detected_summary_json` fuera del contrato principal de lista**

### **Objetivo**

Evitar que el list endpoint siga devolviendo el blob técnico completo.

### **Opciones**

* removerlo del list  
* dejarlo solo en detail  
* o exponerlo solo con `include_technical=true`

### **Archivos probables**

* `position_schemas.py`  
* `positions.py`  
* `shared.py`  
* frontend consumers

### **Criterios de aceptación**

* lista de posiciones ya no depende del blob técnico  
* detail lo expone solo bajo estrategia controlada  
* frontend list view ya no usa summary técnico

---

## **Ticket 3.2 — Crear `technical_snapshot` explícito en detail**

### **Objetivo**

Cuando haga falta debugging/auditoría, exponer un bloque técnico separado y semánticamente claro.

### **Propuesta**

* `technical_snapshot.entity_uid`  
* `technical_snapshot.entity_type`  
* `technical_snapshot.internal_code`  
* `technical_snapshot.review_display_label`  
* `technical_snapshot.raw_qty`  
* `technical_snapshot.qty_parse_status`  
* `technical_snapshot.qty_origin_field`  
* `technical_snapshot.audit`

### **Criterios de aceptación**

* detail separa claramente “público” vs “técnico”  
* no hay duplicados semánticos innecesarios en el bloque principal

---

## **Ticket 3.3 — Rediseñar CSV estándar**

### **Objetivo**

Alinear el CSV con el contrato público limpio.

### **CSV estándar propuesto**

* `inventory_id`  
* `inventory_name`  
* `aisle_id`  
* `aisle_code`  
* `position_id`  
* `position_status`  
* `needs_review`  
* `product_sku`  
* `product_display_label`  
* `barcode` opcional  
* `detected_quantity`  
* `corrected_quantity`  
* `final_quantity`  
* `qty_source`  
* `qty_inference_reason`  
* `traceability_status`  
* `source_image_id`  
* `primary_evidence_id`  
* `updated_at`

### **Archivos probables**

* `backend/src/application/mappers/inventory_export_rows.py`  
* `backend/src/application/use_cases/export_inventory_results.py`  
* `backend/src/application/services/csv_inventory_exporter.py`

### **Criterios de aceptación**

* CSV usa la vista canónica  
* se reducen columnas redundantes  
* tests de snapshot del CSV actualizados

---

## **Ticket 3.4 — Crear CSV técnico opcional**

### **Objetivo**

No perder auditabilidad al limpiar el CSV estándar.

### **Posibles columnas**

* `internal_code`  
* `review_display_label`  
* `raw_qty`  
* `qty_parse_status`  
* `qty_origin_field`  
* `entity_uid`  
* `entity_type`  
* `_audit.explicit_quantity_missing`

### **Criterios de aceptación**

* existe un export técnico separado o flag de export  
* el CSV estándar ya no necesita cargar todo “por las dudas”

---

## **Ticket 3.5 — Test de paridad API vs CSV**

### **Objetivo**

Asegurar que el CSV estándar refleja el contrato canónico.

### **Criterios de aceptación**

* test que compare un caso representativo de `PositionCanonicalView` con fila exportada  
* consolidación/aggregated rows cubiertos  
* qty final consistente entre API y CSV

---

# **Sprint 4 — Limpieza de persistencia, migración y remoción final**

## **Objetivo**

Reducir duplicación persistida y cerrar el cleanup eliminando legacy innecesario.

## **Ticket 4.1 — Definir política final de `detected_summary_json`**

### **Objetivo**

Tomar decisión técnica explícita:

* snapshot inmutable  
* no fuente de contrato público  
* uso permitido: audit/debug/replay

### **Criterios de aceptación**

* política documentada  
* código alineado a esa política  
* ningún serializer público principal depende ya del summary

---

## **Ticket 4.2 — Migrar readers/analytics desde JSON a `product_records`**

### **Objetivo**

Reducir dependencias de consultas SQL sobre `detected_summary_json`.

### **Archivos probables**

* `backend/src/infrastructure/repositories/sql_analytics_repository.py`  
* otros queries/reporting readers

### **Criterios de aceptación**

* queries críticas dejan de usar `JSON_VALUE(detected_summary_json, ...)` cuando corresponda  
* métricas siguen consistentes  
* cobertura de tests/regresión

---

## **Ticket 4.3 — Auditar y limpiar `corrected_summary_json`**

### **Objetivo**

Ver si sigue siendo necesario, cómo se usa y si se puede eliminar o reducir.

### **Criterios de aceptación**

* inventario de readers completo  
* decisión explícita:  
  * mantener  
  * reducir  
  * deprecar  
* plan de migración definido si aplica

---

## **Ticket 4.4 — Resolver persistencia de consolidated/aggregated rows**

### **Objetivo**

Cerrar la brecha entre summary consolidado y `ProductRecord`.

### **Pregunta a responder**

Cuando hay `aggregated_from_ids`, ¿la cantidad final visible debe vivir:

* solo virtualmente en la proyección?  
* o también persistirse en `ProductRecord` representativo?

### **Criterios de aceptación**

* regla funcional cerrada  
* implementación consistente en mapper y persistencia  
* tests para casos consolidados

---

## **Ticket 4.5 — Remover campos legacy del contrato público**

### **Objetivo**

Eliminar definitivamente campos deprecated, una vez migrado frontend.

### **Campos candidatos**

* `sku` legacy top-level  
* `qty`  
* `qtySource`  
* `qtyInferenceReason`  
* `qtyResolved`  
* `detected_summary_json` en list  
* `detected_quantity` si sigue siendo alias redundante

### **Criterios de aceptación**

* frontend ya consume solo `product`, `quantity`, `traceability`  
* documentación y tests actualizados  
* no quedan readers relevantes del shape viejo

---

## **Ticket 4.6 — Limpieza final de export estándar**

### **Objetivo**

Eliminar columnas legacy o redundantes que sobrevivan por compatibilidad.

### **Criterios de aceptación**

* export estándar estable  
* export técnico separado/documentado  
* consumidores internos notificados

---

# **Dependencias entre sprints**

## **Sprint 1 desbloquea**

* contrato nuevo  
* deprecaciones controladas  
* cleanup del CSV

## **Sprint 2 desbloquea**

* remoción del blob técnico del list  
* migración ordenada de frontend

## **Sprint 3 desbloquea**

* limpieza profunda de persistencia  
* remoción final de legacy

## **Sprint 4 cierra**

* la deuda técnica  
* la divergencia entre snapshot y dato canónico  
* el contrato final estable

---

# **Prioridad dentro de cada sprint**

## **Sprint 1**

1. ADR canónica  
2. auditoría de uso en frontend  
3. `PositionCanonicalView`  
4. tests de paridad

## **Sprint 2**

1. bloque `quantity`  
2. bloque `product`  
3. bloque `traceability`  
4. deprecaciones

## **Sprint 3**

1. sacar `detected_summary_json` del list  
2. crear `technical_snapshot`  
3. rediseñar CSV estándar  
4. CSV técnico  
5. test API/CSV

## **Sprint 4**

1. definir política final del summary  
2. migrar analytics/readers  
3. resolver consolidated rows  
4. remover legacy  
5. cleanup final

---

# **Riesgos más importantes por sprint**

## **Sprint 1**

* subestimar dependencias del frontend  
* no cerrar bien la regla de aggregated rows

## **Sprint 2**

* romper contratos si frontend consume top-level legacy  
* ambigüedad sobre si `detected_quantity` sigue siendo necesario

## **Sprint 3**

* list views todavía atadas al blob técnico  
* CSV usado por alguien que esperaba columnas legacy

## **Sprint 4**

* analytics/queries atadas al JSON  
* migración de consolidated rows más compleja que el cleanup superficial

---

# **Definition of Done global**

Esto queda realmente bien resuelto cuando:

* `ProductRecord` es la fuente principal del contrato público para identidad y quantity  
* `detected_summary_json` deja de ser fuente pública principal  
* lista de posiciones no expone blob técnico por defecto  
* detail separa bloque público y técnico  
* CSV estándar se alinea con el contrato público  
* analytics críticos dejan de depender del JSON cuando aplica  
* frontend ya consume `product`, `quantity`, `traceability`  
* campos legacy quedan removidos o muy acotados

---

