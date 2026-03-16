# Bug Investigation: Exceso de `needs_review = true` y rol de `LOOSE_BOXES`

## 1. Executive Summary

**Problema:** Muchos resultados quedan con `needs_review = true`; una parte importante se clasifica directa o indirectamente como `LOOSE_BOXES`, aunque en muchos casos hay etiquetas visibles e información de producto útil.

**Causa raíz probable:** El backend **acopla de forma rígida** el tipo de entidad `LOOSE_BOXES` con la necesidad de revisión. En `count_status.py`, **cualquier** entidad con `entity_type == "LOOSE_BOXES"` recibe `count_status = "INVALID_STRUCTURE"` sin considerar `internal_code`, `position_barcode` ni `product_label_quantity`. El mapper luego traduce `INVALID_STRUCTURE` (y NEEDS_REVIEW, NOT_COUNTABLE) en `needs_review = True`. Así, **la dimensión “estructura logística” (sin pallet) se usa como proxy de “siempre revisar”**, ignorando la dimensión “evidencia de producto”. El prompt puede estar empujando al modelo a clasificar como LOOSE_BOXES más de lo necesario, pero **el fallo de diseño está en backend**: la regla de negocio “LOOSE_BOXES ⇒ revisión” es absoluta y no contempla evidencia de producto suficiente.

---

## 2. Current Flow

Flujo técnico desde el prompt hasta `needs_review`:


| Paso                                       | Ubicación                                                                                                                        | Qué ocurre                                                                                                                                                                                                                                                                                              |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Construcción del prompt                 | `src/llm/prompts.py`                                                                                                             | `_GLOBAL_V21` define los tres entity types (PALLET, EMPTY_PALLET, LOOSE_BOXES). `get_hybrid_prompt(profile_name)` devuelve el texto base (env `HYBRID_PROMPT`, default `global_v21`). Opcionalmente se enriquece con `enrich_prompt_with_image_ids` y/o `enrich_prompt_with_product_label_association`. |
| 2. Envío al modelo                         | `src/pipeline/adapters/gemini_analysis_provider.py`, `src/llm/providers/gemini_provider.py`, `src/llm/gemini_global_analyzer.py` | Se usa `get_hybrid_prompt(...)` para el análisis global. La respuesta JSON del modelo debe cumplir el schema v2.1 (entities con entity_type, model_entity_id, confidence, etc.).                                                                                                                        |
| 3. Validación estructural                  | `src/validation/global_analysis_schema.py`                                                                                       | `validate_global_analysis_structure_v21(data)` exige `entity_type in {PALLET, EMPTY_PALLET, LOOSE_BOXES}` y claves requeridas. No interpreta negocio.                                                                                                                                                   |
| 4. Parseo a entidades                      | `src/parsing/global_analysis_parser.py`                                                                                          | `parse_entities(data, job_id)` convierte cada elemento de `entities` en un `Entity`. `entity_type` viene del JSON (default `"PALLET"` si falta). Se parsean `internal_code`, `position_barcode`, `product_label_quantity`, `has_boxes`, `confidence`, etc. **No se asigna count_status aquí.**          |
| 5. Resolución y asignación de count_status | `src/pipeline/stages/entity_resolution_stage.py`                                                                                 | Tras `parse_entities`, se llama a `assign_count_status(e)` para cada entidad.                                                                                                                                                                                                                           |
| 6. Regla LOOSE_BOXES → needs_review        | `src/decision/count_status.py`                                                                                                   | `assign_count_status(entity)`: si `entity.entity_type == "LOOSE_BOXES"` → **siempre** `entity.count_status = "INVALID_STRUCTURE"`, `entity.final_quantity = None`. **No se consulta** position_barcode, internal_code ni product_label_quantity.                                                        |
| 7. Reporte híbrido                         | `src/reporting/hybrid_report.py`                                                                                                 | `build_hybrid_report(...)` construye el dict del report con `entities` que ya llevan `count_status` (y por tanto INVALID_STRUCTURE para todo LOOSE_BOXES). `_build_summary_from_entities` cuenta `needs_review` y `invalid_structure` a partir de `count_status`.                                       |
| 8. Mapeo a dominio v3                      | `src/infrastructure/pipeline/v3_report_mapper.py`                                                                                | `map_hybrid_report_to_domain(...)` por cada entidad del report: `needs_review = _needs_review_from_entity(entity) or confidence_missing`.                                                                                                                                                               |
| 9. Decisión needs_review en el mapper      | `src/infrastructure/pipeline/v3_report_mapper.py`                                                                                | `_needs_review_from_entity(entity)`: `status = entity.get("count_status")`; devuelve `True` si `status in ("NEEDS_REVIEW", "NOT_COUNTABLE", "INVALID_STRUCTURE") or status == ""`. Por tanto **todo LOOSE_BOXES** (que ya viene con count_status INVALID_STRUCTURE) → **needs_review = True**.          |
| 10. Persistencia                           | `src/application/use_cases/persist_aisle_result.py`, repositorios                                                                | Las `Position` creadas con `needs_review=True` se persisten; la API y el frontend filtran/muestran por `needs_review`.                                                                                                                                                                                  |


**Archivos y funciones clave:**

- Prompt: `src/llm/prompts.py` — `_GLOBAL_V21`, `get_hybrid_prompt()`.
- Validación: `src/validation/global_analysis_schema.py` — `validate_global_analysis_structure_v21`, `ENTITY_TYPES_V21`.
- Parseo: `src/parsing/global_analysis_parser.py` — `parse_entities()` (líneas 141–218; entity_type línea 174).
- Regla de negocio que acopla tipo → revisión: `src/decision/count_status.py` — `assign_count_status()` (líneas 25–28 para LOOSE_BOXES).
- Mapper: `src/infrastructure/pipeline/v3_report_mapper.py` — `_needs_review_from_entity()` (líneas 36–38), `map_hybrid_report_to_domain()` (línea 116).
- Resumen: `src/reporting/hybrid_report.py` — `_build_summary_from_entities`; `src/review/review_merge.py` — `_summary_from_entity_dicts` (cuenta needs_review por count_status).

---

## 3. Findings

### 3.1 Dónde se marca needs_review

- **Único lugar donde se asigna el booleano `needs_review` a una posición:** `v3_report_mapper.map_hybrid_report_to_domain`, línea 116:  
`needs_review = _needs_review_from_entity(entity) or confidence_missing`
- `**_needs_review_from_entity`** (líneas 36–38): devuelve True si `count_status` está en `("NEEDS_REVIEW", "NOT_COUNTABLE", "INVALID_STRUCTURE")` o es cadena vacía. No mira `entity_type` ni evidencia de producto.

### 3.2 Cómo influye LOOSE_BOXES en el pipeline

- **En `count_status.py`:** `entity_type == "LOOSE_BOXES"` → **siempre** `count_status = "INVALID_STRUCTURE"`, `final_quantity = None`. Es la única rama que no depende de position_barcode, internal_code ni product_label_quantity.
- **En `quality_score.py`:** El bonus `+0.1` por “has_boxes” solo aplica cuando `entity_type == "PALLET"`. LOOSE_BOXES no recibe ese bonus aunque tenga has_boxes.
- **En el mapper:** INVALID_STRUCTURE → needs_review True. Por tanto **todo LOOSE_BOXES termina con needs_review=True** independientemente de etiquetas o cantidades.

### 3.3 Semántica actual de LOOSE_BOXES

- **En el prompt:** “LOOSE_BOXES: grouped boxes without pallet (do NOT count as pallet).” Se define como **tipo estructural** (cajas sin pallet).
- **En el dominio:** `Entity.entity_type` es PALLET | EMPTY_PALLET | LOOSE_BOXES; no hay subtipos ni flags de “tiene evidencia de producto”.
- **En la regla de negocio:** El sistema trata LOOSE_BOXES como **siempre** INVALID_STRUCTURE y por tanto **siempre** needs_review. No se distingue “cajas sueltas sin identificación” de “cajas sueltas con etiqueta/SKU legible”.

**Conclusión:** Hoy **sí** se mezclan conceptos: “no hay pallet” (estructura) se usa como proxy de “requiere revisión” (decisión operativa), sin considerar “hay etiqueta/producto identificable” (evidencia).

### 3.4 Contradicción entre clasificación estructural y evidencia de producto

- **Sí puede ocurrir** que una entidad tenga `entity_type = "LOOSE_BOXES"` y a la vez `internal_code`, `position_barcode` o `product_label_quantity` poblados (el schema y el parser lo permiten; el prompt no prohíbe reportar labels en LOOSE_BOXES).
- **assign_count_status** para LOOSE_BOXES **no lee** esos campos; asigna INVALID_STRUCTURE en el primer `if entity_type == "LOOSE_BOXES"` y hace `return`.
- **Efecto:** Esa entidad se manda a revisión **solo por la estructura** (LOOSE_BOXES), aunque tenga evidencia suficiente para poder ser auto-aceptada o contada. El fallo está en **la capa de decisión (count_status)**, no en el parseo ni en el schema.

### 3.5 Duplicación / conservadurismo

- **Prompt:** Dice “do NOT count as pallet” para LOOSE_BOXES; no dice “siempre revisar” ni “no reportar SKU”.
- **Backend:** Traduce “LOOSE_BOXES” en “siempre INVALID_STRUCTURE → siempre needs_review”. La regla conservadora está **solo en backend**; el prompt no define explícitamente esa consecuencia.

### 3.6 Resumen de hallazgos


| Hallazgo                                                                           | Ubicación                                                             |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| LOOSE_BOXES ⇒ INVALID_STRUCTURE incondicional                                      | `count_status.py` líneas 25–28                                        |
| INVALID_STRUCTURE ⇒ needs_review True                                              | `v3_report_mapper.py` _needs_review_from_entity                       |
| assign_count_status no mira evidencia de producto para LOOSE_BOXES                 | `count_status.py` rama LOOSE_BOXES                                    |
| quality_score no da bonus por has_boxes a LOOSE_BOXES                              | `quality_score.py` línea 35 (solo PALLET)                             |
| Parser y schema permiten internal_code/position_barcode/product_qty en LOOSE_BOXES | `global_analysis_parser.py`, `global_analysis_schema.py`, `EntityV21` |


---

## 4. Root Cause Analysis

**Por qué tantos casos terminan en review:**

1. **Regla fija en backend:** Cualquier entidad clasificada por el modelo como LOOSE_BOXES recibe INVALID_STRUCTURE y por tanto needs_review=True, sin excepciones.
2. **Modelo puede estar sobre-clasificando LOOSE_BOXES:** Si el prompt o el contexto llevan al modelo a elegir LOOSE_BOXES cuando hay duda (p. ej. pallet poco claro, cajas apiladas sin base visible), aumenta el volumen de LOOSE_BOXES y por tanto de needs_review.
3. **Evidencia de producto no mitiga:** Aunque la entidad tenga internal_code o position_barcode, la rama LOOSE_BOXES en assign_count_status no los usa; la decisión es puramente por entity_type.
4. **Confianza faltante también fuerza review:** `_needs_review_from_entity` se combina con `confidence_missing`; si confidence falta o es inválida, también se marca needs_review. Eso es independiente de LOOSE_BOXES pero suma más casos.

La **causa raíz principal** es el **acoplamiento en backend** entre “entity_type = LOOSE_BOXES” y “needs_review = True”, sin considerar evidencia de producto. La sobre-clasificación de LOOSE_BOXES por el modelo puede agravar el síntoma pero no es la única causa.

---

## 5. Domain Design Problem

**Dimensiones que deberían estar separadas:**

- **Entity structure type:** PALLET / EMPTY_PALLET / LOOSE_BOXES (qué se vio: pallet, pallet vacío, cajas sin pallet).
- **Product evidence presence:** ¿Tiene internal_code, position_barcode, product_label_quantity usable?
- **Review necessity:** ¿Requiere revisión manual o puede auto-aceptarse / contarse?

**Problema actual:** La necesidad de revisión se deriva **solo** de count_status, y count_status para LOOSE_BOXES se fija **solo** por entity_type. No hay una dimensión explícita “tiene evidencia de producto suficiente” que modere la decisión de revisión para LOOSE_BOXES. Es decir, **estructura y necesidad de revisión están acopladas de forma incorrecta**; la evidencia de producto no entra en la regla para LOOSE_BOXES.

---

## 6. Solution Options

### Opción A: Mantener LOOSE_BOXES pero cambiar la regla de needs_review (desacoplar en backend)

- **Idea:** En `assign_count_status`, para LOOSE_BOXES no asignar siempre INVALID_STRUCTURE. Por ejemplo: si tiene position_barcode o internal_code y product_label_quantity (o criterio similar), asignar COUNTED o NEEDS_REVIEW según evidencia; si no tiene evidencia útil, INVALID_STRUCTURE.
- **Ventajas:** No cambia el contrato del modelo ni el schema; solo la lógica de negocio. Reduce needs_review cuando hay evidencia.
- **Riesgos:** Definir umbral “evidencia suficiente” para LOOSE_BOXES; posible desalineación con operaciones si el criterio es distinto al de PALLET.
- **Impacto:** `count_status.py` (y posiblemente tests). Reportes y resúmenes se adaptan porque ya dependen de count_status.
- **Datos existentes:** No se re-procesan jobs pasados; solo nuevos resultados cambiarían.

### Opción B: Ajustar solo el prompt (reducir uso de LOOSE_BOXES)

- **Idea:** Aclarar en el prompt que LOOSE_BOXES debe usarse solo cuando **realmente** no hay estructura de pallet y no hay etiquetas de posición/producto utilizables; si hay etiquetas legibles, preferir PALLET (o guiar al modelo a no usar LOOSE_BOXES salvo casos claros).
- **Ventajas:** Menos entidades clasificadas como LOOSE_BOXES, menos INVALID_STRUCTURE y menos needs_review por esa vía.
- **Riesgos:** El modelo puede seguir devolviendo LOOSE_BOXES en casos ambiguos; la regla backend sigue siendo “todo LOOSE_BOXES ⇒ review”. No desacopla estructura vs. evidencia.
- **Impacto:** `src/llm/prompts.py`, posiblemente tests de prompt/schema.
- **Datos existentes:** Sin cambio en lógica backend, datos históricos no cambian.

### Opción C: Introducir dimensión explícita “product evidence” y usarla en la regla de revisión

- **Idea:** Definir un predicado “has_sufficient_product_evidence(entity)” (p. ej. internal_code o position_barcode presentes y/o product_label_quantity no nulo). En assign_count_status: para LOOSE_BOXES, si has_sufficient_product_evidence → asignar COUNTED o NEEDS_REVIEW según cantidad/coherencia; si no → INVALID_STRUCTURE. Opcionalmente usar el mismo concepto en _needs_review_from_entity o en una capa intermedia para no marcar needs_review cuando hay evidencia suficiente aunque count_status sea NEEDS_REVIEW/INVALID_STRUCTURE (según diseño elegido).
- **Ventajas:** Separa claramente “tipo estructural” de “evidencia de producto” y “necesidad de revisión”; dominio más claro y extensible.
- **Riesgos:** Más cambios (dominio, reglas, tests); hay que definir “suficiente” y mantener coherencia con PALLET.
- **Impacto:** `count_status.py`, posiblemente `v3_report_mapper.py`, `Entity` o DTOs si se expone el flag, tests.
- **Datos existentes:** Igual que A/B, solo nuevos runs.

### Opción D: Subtipos o flags para LOOSE_BOXES (p. ej. LOOSE_BOXES_WITH_LABELS)

- **Idea:** En el schema/prompt, distinguir LOOSE_BOXES “con etiqueta” vs “sin etiqueta”, o añadir un flag en la entidad; backend usa eso para no marcar INVALID_STRUCTURE cuando hay etiqueta.
- **Ventajas:** Semántica explícita en el contrato modelo/API.
- **Riesgos:** Cambio de contrato (schema, validación, parser, posiblemente API); el modelo debe rellenar el nuevo campo de forma estable.
- **Impacto:** Validación, parser, count_status, mapper, documentación, frontend si se muestra.

**Recomendación:** La opción que mejor corrige la causa raíz y el diseño de dominio es **Opción C** (o una variante de **A** que formalice “evidencia suficiente” para LOOSE_BOXES). **A** es el cambio mínimo en backend; **C** es la solución más clara a largo plazo. **B** sola es insuficiente porque no desacopla estructura y revisión. **D** es más invasiva (cambio de contrato).

---

## 7. Recommended Fix

- **Causa raíz principal:** Regla en backend que hace que **todo** LOOSE_BOXES sea INVALID_STRUCTURE y por tanto needs_review, sin considerar evidencia de producto.
- **Solución técnica recomendada:** Desacoplar en backend (Opción A/C):
  - En `assign_count_status`, para `entity_type == "LOOSE_BOXES"`:
    - Si la entidad tiene evidencia de producto suficiente (p. ej. `internal_code` o `position_barcode` presentes, y opcionalmente `product_label_quantity` o coherencia con has_boxes), **no** asignar INVALID_STRUCTURE; asignar COUNTED si hay position + cantidad, o NEEDS_REVIEW si solo hay parte de la evidencia (alineado con la lógica actual de PALLET).
    - Si no tiene evidencia suficiente, mantener INVALID_STRUCTURE (y por tanto needs_review).
  - Mantener el mismo entity_type y schema; no obligar a cambiar el prompt como primer paso (se puede refinar después para reducir ruido en LOOSE_BOXES).
- **Por qué respeta mejor el dominio:** Trata “tipo estructural” y “evidencia de producto” como dimensiones distintas; la necesidad de revisión depende de ambas, no solo de que sea LOOSE_BOXES.
- **Partes a modificar:** `src/decision/count_status.py` (rama LOOSE_BOXES); tests en `tests/test_stage_2_1_a.py` y `tests/infrastructure/pipeline/test_v3_report_mapper_and_persist.py` y cualquier otro que asuma “LOOSE_BOXES ⇒ siempre INVALID_STRUCTURE”. Opcional: `quality_score.py` para dar bonus por has_boxes también a LOOSE_BOXES cuando aplique.
- **Tests que deberían existir antes de tocar código:** (1) Entidad LOOSE_BOXES con internal_code y product_label_quantity → count_status no INVALID_STRUCTURE y needs_review False (o NEEDS_REVIEW/COUNTED según criterio acordado). (2) Entidad LOOSE_BOXES sin internal_code ni position_barcode → count_status INVALID_STRUCTURE, needs_review True. (3) Regresión: PALLET y EMPTY_PALLET se comportan igual que hoy.

---

## 8. Safe Implementation Plan

1. **Definir criterio “evidencia suficiente” para LOOSE_BOXES** (p. ej. igual que para PALLET: position_barcode o internal_code; y para COUNTED: position + product_label_quantity). Documentarlo en count_status o en un módulo de reglas.
2. **Añadir tests** que fijen el comportamiento deseado para LOOSE_BOXES con y sin evidencia (y regresión PALLET/EMPTY_PALLET).
3. **Cambiar solo la rama LOOSE_BOXES en `assign_count_status`**: aplicar lógica análoga a PALLET cuando haya evidencia suficiente; si no, mantener INVALID_STRUCTURE.
4. **Re-ejecutar tests existentes** (count_status, mapper, reporting, review_merge) y corregir los que asuman “LOOSE_BOXES ⇒ siempre INVALID_STRUCTURE”.
5. **Opcional:** Revisar prompt para reducir clasificaciones LOOSE_BOXES cuando haya pallet o etiquetas claras (sin cambiar el contrato de salida).
6. **No tocar** en esta fase: schema v2.1 (entity_type sigue siendo tres valores), parser estructural, formato de hybrid_report.json.

---

## 9. Tests to Add Before and After the Fix

**Antes de implementar (para fijar comportamiento deseado):**

- `test_assign_count_status_loose_boxes_with_internal_code_and_qty` — LOOSE_BOXES con internal_code y product_label_quantity (y opcionalmente position_barcode) → count_status COUNTED (o NEEDS_REVIEW si se decide ser conservador), no INVALID_STRUCTURE; y en mapper → needs_review False (o según criterio).
- `test_assign_count_status_loose_boxes_with_position_barcode_only` — LOOSE_BOXES con position_barcode pero sin cantidad → count_status NEEDS_REVIEW, no INVALID_STRUCTURE.
- `test_assign_count_status_loose_boxes_no_evidence` — LOOSE_BOXES sin internal_code ni position_barcode → count_status INVALID_STRUCTURE, needs_review True (comportamiento actual).
- `test_map_hybrid_report_loose_boxes_with_evidence_no_needs_review` — Integración: report con entidad LOOSE_BOXES con internal_code/product_label_quantity → Position.needs_review False (o según criterio).

**Regresión (después del cambio):**

- Tests existentes de assign_count_status para PALLET y EMPTY_PALLET sin cambios.
- `test_map_hybrid_report_needs_review` y tests que esperan needs_review True para count_status NEEDS_REVIEW / INVALID_STRUCTURE, ajustados solo donde se introduzca el nuevo comportamiento para LOOSE_BOXES con evidencia.

---

## Restricciones y aclaraciones

- **No se implementó código** en esta investigación; solo análisis y recomendaciones.
- **Hipótesis vs hechos:** Los “hallazgos” están basados en lectura de código y flujo trazado. La afirmación de que “muchos casos tienen etiquetas visibles” es la del usuario; la causa técnica (regla backend incondicional para LOOSE_BOXES) está verificada en código.
- **Lógica duplicada:** La regla “LOOSE_BOXES ⇒ revisión” está **solo en backend** (count_status → INVALID_STRUCTURE; mapper → needs_review). El prompt no define esa consecuencia.
- **LOOSE_BOXES como proxy:** Sí; hoy el sistema usa LOOSE_BOXES como proxy de “caso que siempre requiere revisión” sin considerar evidencia de producto, lo que se considera mala modelización del dominio en este análisis.

