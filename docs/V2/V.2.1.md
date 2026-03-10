# **Dinamic Systems**

# **Versión 2.1 — Etapa 2.1.A**

# **Structural & Label-Aware Foundation (Redesign)**

---

# **1️⃣ Objetivo Estratégico**

La etapa 2.1.A establece la nueva base conceptual del sistema híbrido.

A partir de esta etapa, el sistema deja de ser solamente un “contador visual” y pasa a ser un:

Sistema estructural consciente de entidades logísticas reales.

El modelo debe:

* Identificar correctamente unidades físicas.  
* Clasificar su tipo estructural.  
* Extraer información visible de etiquetas.  
* Determinar estados de inventario sin inferencias artificiales.  
* Preparar identificación determinista del pallet.

Esta etapa redefine el dominio.

---

# **2️⃣ Cambio Conceptual Central**

En v2.0 el sistema detectaba:

```
Pallets
```

En v2.1.A el sistema detecta:

```
Entidades logísticas estructurales
```

Las entidades pueden ser:

* PALLET  
* EMPTY\_PALLET  
* LOOSE\_BOXES

Esto elimina ambigüedad estructural.

---

# **3️⃣ Arquitectura Base (sin cambiar número de llamadas)**

Se mantiene el flujo híbrido :

```
Video
 → extract_representative_frames()
 → Gemini (una sola llamada global)
 → validate_schema_v2_1
 → parse_entities()
 → resolve_pallet_id()
 → assign_count_status()
 → build_hybrid_report_v2_1()
```

No se agregan llamadas.  
No se agrega OCR externo.  
No se agrega tracking.

---

# **4️⃣ Nuevo Dominio de Entidad**

## **4.1 Entity Types**

### **PALLET**

* Se observa estructura física de pallet.  
* Puede tener cajas.  
* Puede tener etiqueta o no.

### **EMPTY\_PALLET**

* Estructura visible.  
* Sin cajas encima.

### **LOOSE\_BOXES**

* Cajas agrupadas.  
* No existe estructura clara de pallet.  
* No debe contarse como pallet.

---

# **5️⃣ Nuevo Schema Global (Obligatorio)**

Gemini debe devolver:

```json
{
  "total_entities_detected": 3,
  "entities": [
    {
      "entity_type": "PALLET | EMPTY_PALLET | LOOSE_BOXES",
      "model_entity_id": "E1",

      "position_barcode": "string|null",
      "position_label_text": "string|null",

      "product_label_text": "string|null",
      "product_label_quantity": "int|null",

      "has_boxes": true,
      "confidence": 0.92
    }
  ]
}
```

Reglas estrictas:

* No inventar texto.  
* No inferir cantidades no visibles.  
* No duplicar entidades.  
* No crear pallets ocultos.

---

# **6️⃣ Resolución Determinista del pallet\_id**

Regla definitiva de identificación:

```
1. Si position_barcode válido → pallet_id = barcode
2. Else si position_label_text válido → pallet_id = normalizado(text)
3. Else → pallet_id = PALLET_XXX (incremental)
```

### **Garantías**

* Unicidad por job.  
* Determinismo.  
* Estabilidad entre ejecuciones.

---

# **7️⃣ Nuevo Modelo de Dominio**

```py
@dataclass
class Entity:

    entity_type: str  # PALLET | EMPTY_PALLET | LOOSE_BOXES

    pallet_id: str
    pallet_id_method: str  # position_barcode | position_ocr | generated

    position_barcode: Optional[str]
    position_label_text: Optional[str]

    product_label_text: Optional[str]
    product_label_quantity: Optional[int]

    has_boxes: bool
    confidence: float

    count_status: str  # COUNTED | NEEDS_REVIEW | NOT_COUNTABLE | EMPTY | INVALID_STRUCTURE
    final_quantity: Optional[int]
```

---

# **8️⃣ Lógica de Estados (Reescrita)**

## **Caso 1 — EMPTY\_PALLET**

```
count_status = EMPTY
final_quantity = 0
```

No fallback.

---

## **Caso 2 — LOOSE\_BOXES**

```
count_status = INVALID_STRUCTURE
```

Excluido del inventario.

---

## **Caso 3 — PALLET**

### **Subcaso A — Tiene posición \+ cantidad visible**

```
count_status = COUNTED
final_quantity = product_label_quantity
```

---

### **Subcaso B — Tiene posición pero no cantidad**

```
count_status = NEEDS_REVIEW
```

---

### **Subcaso C — No tiene posición ni cantidad**

```
count_status = NOT_COUNTABLE
```

No se ejecuta fallback.

---

# **9️⃣ Qué NO Hace 2.1.A**

* No hace conteo visual automático.  
* No hace OCR externo.  
* No hace inferencia probabilística.  
* No agrupa cajas sueltas como pallet.  
* No inventa información.

Es una etapa estructural.

---

# **🔟 Cambios Reales en Código**

Archivos a modificar:

* `global_pallet_analysis_prompt.py`  
* `global_analysis_schema.py`  
* `global_analysis_parser.py`  
* `domain/pallet.py` (ahora Entity)  
* `hybrid_report.py`

Se elimina dependencia conceptual de “solo pallets”.

---

# **1️⃣1️⃣ Riesgos**

### **Riesgo 1**

Gemini mezcle texto entre pallets.

Mitigación:

* Prompt restrictivo.  
* Validación cruzada.

### **Riesgo 2**

Clasificación errónea de LOOSE\_BOXES.

Mitigación:

* Reglas claras en prompt.  
* Revisión de confianza.

---

# **1️⃣2️⃣ Definition of Done**

2.1.A está completa cuando:

* El sistema distingue correctamente:  
  * PALLET  
  * EMPTY\_PALLET  
  * LOOSE\_BOXES  
* El `pallet_id` se basa en etiqueta cuando existe.  
* No se incrementan llamadas Gemini.  
* No se rompe compatibilidad con worker actual.  
* El reporte híbrido refleja nueva estructura.

---

# **🎯 Resultado Estratégico**

Después de esta redefinición:

* El sistema entiende la estructura real del depósito.  
* El pallet deja de ser una suposición.  
* La base está lista para:  
  * 2.1.B → barcode robusto opcional  
  * 2.1.C → extracción de texto mejorada (ya integrada)  
  * 2.1.D → evidencia estructurada  
  * 2.1.E → endpoint manual

---

# 

# **Versión 2.1 — Etapa 2.1.B**

# **Position Barcode Hardening (Local \+ Multi-Frame, Optional)**

---

## **1\. Objetivo**

La etapa **2.1.B** refuerza la identificación de la **etiqueta de posición** cuando existe un **barcode/QR**, para maximizar:

* estabilidad del `pallet_id` (identificador real de negocio),  
* reducción de `pallet_id` generados,  
* menor ambigüedad y menor dependencia del texto.

**Importante:** en el rediseño v2.1, el sistema ya intenta extraer `position_barcode` desde la llamada global a Gemini (Etapa 2.1.A).  
2.1.B agrega un **refuerzo local determinista** que se ejecuta **solo si es necesario** (policy-driven).

---

## **2\. Principio de diseño**

**LLM-first, deterministic-when-needed**:

* Gemini global entrega una primera lectura (`position_barcode`).  
* Si el valor es `null` o dudoso → se intenta lectura local multi-frame (barcode decoding).  
* Si local obtiene un resultado sólido → se promueve a `position_barcode`.  
* Si no → se mantiene lo que vino de Gemini (o queda missing).

Esta etapa no agrega llamadas a Gemini.

---

## **3\. Alcance**

Incluye:

* Política de disparo del “barcode hardening”.  
* Selección de frames candidatos por nitidez y no redundancia.  
* Decodificación local de barcode/QR sobre crops (multi-frame).  
* Consolidación por consenso (anti-falsos positivos).  
* Integración con `resolve_pallet_id()`.

No incluye:

* OCR externo.  
* Tracking por frame.  
* Entrenamiento de modelos.  
* Evidencia avanzada (eso va en 2.1.D).

---

## **4\. Integración en el pipeline híbrido**

Flujo v2.1 (parcial):

```
Video
 → extract_representative_frames()
 → Gemini Global (entities + labels)
 → validate_schema_v2_1
 → parse_entities()
 → (2.1.B) barcode_hardening_if_needed()
 → resolve_pallet_id()
 → assign_count_status()
 → build_report_v2_1()
```

---

## **5\. Política de disparo (Barcode Hardening Policy)**

El hardening se ejecuta por entidad `PALLET` cuando:

* `position_barcode == null`, o  
* `position_barcode` es “sospechoso” (p.ej. muy corto, caracteres inválidos), o  
* `confidence` global es baja y hay indicios de etiqueta visible, o  
* `position_label_text` existe pero el barcode es null (indicador de que hay etiqueta pero no se leyó el código).

**No se ejecuta** para:

* `EMPTY_PALLET`  
* `LOOSE_BOXES`  
* entidades `PALLET` marcadas como `NOT_COUNTABLE` por ausencia total de señales de etiqueta (según heurística simple).

---

## **6\. Selección de frames candidatos (multi-frame)**

Dado el set de frames representativos (ya filtrados por blur/redundancia en v2.0 ), para cada entidad:

1. elegir frames donde **la etiqueta de posición** sea más probable (según lo que venga de Gemini o heurística de región típica),  
2. rankear frames por:  
   * nitidez (varianza Laplaciana),  
   * “tamaño aparente” de la región (si hay bbox estimada),  
   * baja redundancia (pHash/dHash),  
3. seleccionar top-K (recomendado K=5, con máximo configurable).

---

## **7\. Extracción de región de barcode**

2 caminos posibles (dependiendo de lo que tengamos en 2.1.A):

### **7.1 Si Gemini devuelve bbox (recomendado para 2.1.A+)**

* usar bbox de `position_label_bbox` (si existe) y recortar directo.

### **7.2 Si Gemini NO devuelve bbox (mínimo viable)**

* usar heurística:  
  * buscar zona con alto contraste \+ patrón lineal (barcode) dentro de regiones tipo “etiqueta”,  
  * o región típica (por ejemplo laterales/altura donde suelen pegarla),  
  * y recortar candidatos (N crops por frame).

Nota: si querés mantener esto limpio, la recomendación es **extender el schema v2.1.A para incluir bbox** de la etiqueta de posición. Eso vuelve 2.1.B mucho más determinista.

---

## **8\. Decodificación local**

Se usa una librería de decodificación de barcode/QR (ej. ZXing / zbar / pyzbar), devolviendo:

* `decoded_value`  
* `symbology` (EAN, Code128, QR, etc. si disponible)  
* `decode_score` (si disponible)

Se hacen intentos por crop:

* preprocesamiento liviano:  
  * grayscale  
  * contraste  
  * binarización adaptativa  
  * rotaciones leves (±5°, ±10°)

---

## **9\. Consolidación por consenso (anti-falsos positivos)**

Si hay múltiples lecturas (por frames y por transforms):

1. agrupar por `decoded_value`  
2. elegir el valor con:  
   * mayor cantidad de apariciones (votes),  
   * y mejor score promedio si existe.

### **Reglas de aceptación**

* **Aceptar** si `votes >= 2` (aparece al menos en 2 lecturas independientes), o  
* **Aceptar** si `votes == 1` pero el valor pasa validación de formato estricta y proviene de un frame de alta nitidez.

### **Reglas de rechazo / conflicto**

* Si hay 2+ valores con votos similares → `barcode_conflict`  
* En conflicto:  
  * no se pisa lo que vino de Gemini,  
  * se marca para revisión (`NEEDS_REVIEW`) si afecta identificación.

---

## **10\. Validación de formato (configurable por cliente)**

Para evitar falsos positivos, el sistema debe validar:

* longitud mínima/máxima,  
* set de caracteres permitido,  
* prefijo esperado (ej. `POS-`, `RACK-`, numérico puro, etc.),  
* checksum si el estándar lo incluye (EAN13, etc. cuando aplique).

Esto debe ser parametrizable por `customer_profile`.

---

## **11\. Actualización de entidad y resolución del pallet\_id**

Si hardening logra barcode válido:

* `position_barcode = decoded_value`  
* `position_barcode_source = local_decoder`  
* `pallet_id_method = position_barcode`  
* `pallet_id = position_barcode`

Si falla:

* mantener `position_barcode` de Gemini (si existía),  
* o queda null y se continúa con `position_label_text` / generado.

---

## **12\. Métricas de la etapa (observabilidad mínima)**

Agregar al reporte/metrics interno:

* `barcode_hardening_attempts`  
* `barcode_hardening_success`  
* `barcode_hardening_conflicts`  
* `barcode_hardening_failures`

Opcional por entidad:

* `barcode_votes`  
* `barcode_best_score`

---

## **13\. Riesgos y mitigaciones**

### **Motion blur / vibración**

* mitigación: rankear por nitidez \+ multi-frame

### **Reflejos / plastic wrap**

* mitigación: varios frames \+ varias transformaciones

### **Falsos positivos**

* mitigación: validación de formato \+ consenso

### **No hay bbox de etiqueta**

* mitigación: extender schema en 2.1.A para incluir bbox (recomendación fuerte)

---

## **14\. Definition of Done**

2.1.B se considera completada cuando:

* Para videos con etiquetas de posición, el % de pallets con `pallet_id_method = position_barcode` aumenta significativamente vs 2.1.A.  
* El sistema no incrementa llamadas a Gemini.  
* No introduce falsos positivos masivos (validación \+ consenso).  
* Mantiene determinismo: mismo video → mismo `pallet_id` (si barcode visible).

---

## **15\. Resultado estratégico**

Después de 2.1.B:

* La identificación del pallet se vuelve más confiable ante fallos del LLM.  
* Se reduce la dependencia de texto y generación incremental.  
* Se mejora la integrabilidad con WMS / ubicaciones reales.

---

# **Versión 2.1 — Etapa 2.1.D**

# **Evidence Pack Generation (Per-Pallet \+ Per-Product)**

---

## **1\. Objetivo**

La etapa **2.1.D** incorpora generación de **evidencia estructurada** para cada entidad detectada (principalmente `PALLET`) con el fin de:

* auditar resultados,  
* soportar corrección manual / asistida sin re-procesar el video,  
* habilitar el endpoint de conteo específico,  
* evitar “fallbacks” inventados cuando faltan etiquetas.

En términos operativos:

Si el sistema no puede contar con certeza, debe dejar evidencia clara y accionable.

---

## **2\. Contexto (v2.1.A \+ v2.1.B)**

Luego de 2.1.A:

* El sistema detecta `entities` (`PALLET`, `EMPTY_PALLET`, `LOOSE_BOXES`).  
* Extrae `position_barcode`, `position_label_text`, `product_label_text`, `product_label_quantity`.  
* Resuelve `pallet_id` con prioridad posición, y determina `count_status`.

Luego de 2.1.B (opcional):

* Refuerza `position_barcode` con un decoder local multi-frame.

**2.1.D no agrega llamadas a Gemini.**  
Usa los frames ya extraídos por `extract_representative_frames()` .

---

## **3\. Alcance**

Incluye:

* Selección determinista de frames “mejores” por entidad.  
* Export de imágenes por entidad:  
  * frames representativos  
  * crops de etiqueta de posición  
  * crops de etiqueta de producto  
  * crops “por producto/caja” (si aplicable al flujo actual)  
* Deduplicación de evidencia para controlar tamaño.  
* Contrato estable de “evidence index” (JSON) para consumo por API.

No incluye:

* Endpoint manual (2.1.E).  
* Persistencia en DB (si aún no está).  
* Tracking por frame (si no existe).  
* Identificación SKU fina por visión (eso es otro módulo).

---

## **4\. Principios de diseño**

1. **Determinismo**: mismo video → mismo set de evidencia (salvo cambios de config).  
2. **Accionable**: evidencia debe servir para decidir y corregir.  
3. **Eficiencia**: evitar guardar miles de frames redundantes.  
4. **Trazabilidad**: cada imagen se relaciona a `pallet_id` y a su razón (`label`, `product`, `overview`).

---

## **5\. Estructura de salida (filesystem)**

Dentro del run dir del job:

```
output/<job_id>/run/
  hybrid_report.json
  hybrid_report.csv
  evidence/
    pallet_<pallet_id>/
      overview/
        best_000.jpg
        best_001.jpg
        best_002.jpg
      position_label/
        pos_label_best.jpg
        pos_label_candidates/
          pos_label_000.jpg
          pos_label_001.jpg
      product_label/
        prod_label_best.jpg
        prod_label_candidates/
          prod_label_000.jpg
          prod_label_001.jpg
      products/
        product_001/
          best.jpg
          crops/
          frames/
```

Notas:

* Si `pallet_id` tiene caracteres raros, se aplica **slug** seguro para path.  
* Para `EMPTY_PALLET` o `LOOSE_BOXES`, se guarda solo `overview/`.

---

## **6\. Selección de “Best Frames” (Overview)**

Para cada entidad, seleccionar `K_overview` frames (ej. 3\) que representen mejor la escena.

### **Scoring propuesto (determinista)**

Para cada frame candidato:

* **Sharpness score**: varianza Laplaciana (más alto, mejor).  
* **Diversity**: evitar duplicados con dHash/pHash (distancia Hamming mínima).  
* **Entity salience** (si tenemos bbox): mayor área relativa del bbox.

Selección:

1. ordenar por score total,  
2. elegir top,  
3. filtrar por diversidad (no near-duplicates).

---

## **7\. Evidencia de etiquetas**

### **7.1 Position label evidence**

* `pos_label_candidates/`: hasta `K_pos_candidates` (ej. 5\) crops candidatos.  
* `pos_label_best.jpg`: el mejor crop (más nítido \+ mayor contraste \+ si barcode decode success, prioridad).

**Si 2.1.B encuentra barcode**, el crop que lo logró debe ser priorizado como “best”.

### **7.2 Product label evidence**

* `prod_label_candidates/`: hasta `K_prod_candidates` (ej. 5).  
* `prod_label_best.jpg`: mejor crop según nitidez \+ legibilidad (heurística simple: contraste \+ densidad de bordes).

---

## **8\. Evidencia por producto/caja (cuando aplique)**

Esta sección depende de tu capacidad actual de “detectar cajas” dentro del pallet.  
Como en hybrid puro no hay detección por frame, en 2.1.D lo planteamos así:

### **Modalidad mínima (si NO hay detección de cajas todavía)**

* No se crean subcarpetas `products/product_XXX/`.  
* Se guarda evidencia general del pallet (`overview`) \+ etiquetas.

### **Modalidad extendida (si ya hay detector/crops disponibles en tu stack)**

* Para cada cluster de caja/crop:  
  * elegir `best.jpg`  
  * guardar `crops/` y `frames/` asociados

Esto deja el sistema listo para el endpoint de conteo específico.

---

## **9\. Control de costos (tamaño de evidencia)**

Para evitar explosión de storage:

* `K_overview = 3` (default)  
* `K_pos_candidates = 5`  
* `K_prod_candidates = 5`  
* `MAX_TOTAL_IMAGES_PER_PALLET` (ej. 25\)  
* Deduplicación por hash para no guardar similares  
* JPEG quality configurable (ej. 85\)

---

## **10\. Evidence Index (Contrato estable)**

Además de imágenes, se genera un índice JSON por entidad.

Ruta:

```
output/<job_id>/run/evidence_index.json
```

Estructura:

```json
{
  "job_id": "J123",
  "mode": "hybrid_v2.1",
  "entities": [
    {
      "pallet_id": "POS-000123",
      "entity_type": "PALLET",
      "count_status": "NEEDS_REVIEW",
      "evidence": {
        "overview": [
          "evidence/pallet_POS-000123/overview/best_000.jpg",
          "evidence/pallet_POS-000123/overview/best_001.jpg"
        ],
        "position_label_best": "evidence/pallet_POS-000123/position_label/pos_label_best.jpg",
        "position_label_candidates": [
          "evidence/pallet_POS-000123/position_label/pos_label_candidates/pos_label_000.jpg"
        ],
        "product_label_best": "evidence/pallet_POS-000123/product_label/prod_label_best.jpg",
        "product_label_candidates": []
      }
    }
  ]
}
```

Este índice es el contrato que consumirá 2.1.E.

---

## **11\. Reglas por estado (qué evidencia guardar)**

### **COUNTED**

* overview (mínimo)  
* best de etiquetas (posición \+ producto)

### **NEEDS\_REVIEW**

* overview (3)  
* etiquetas (best \+ candidates)

### **NOT\_COUNTABLE**

* overview (3)  
* cualquier candidato de etiqueta si existiera (aunque no legible)  
* prioridad: evidencia para corrección manual

### **EMPTY**

* overview (2–3)  
* sin productos/etiquetas salvo que existan

### **INVALID\_STRUCTURE**

* overview (2–3)  
* marcado como excluido

---

## **12\. Impacto en Reporte v2.1**

Se agrega por entidad:

* `evidence_path` (carpeta base)  
* opcional: referencias directas a best images

Ejemplo:

```json
{
  "pallet_id": "PALLET_003",
  "count_status": "NOT_COUNTABLE",
  "evidence_path": "evidence/pallet_PALLET_003/"
}
```

---

## **13\. Cambios en código (módulos)**

Sugerencia de módulos:

* `src/evidence/evidence_pack.py`  
  * `generate_evidence_pack(job_id, frames, entities, run_dir) -> EvidenceIndex`  
* `src/evidence/scoring.py`  
  * `score_frame_sharpness(frame)`  
  * `dedupe_by_hash(images)`  
* `src/evidence/paths.py`  
  * slug/normalización de paths

Integración desde `hybrid_inventory_pipeline.py` al final, antes de escribir el reporte.

---

## **14\. Riesgos y mitigaciones**

### **Riesgo: evidencia inútil (borrosa)**

* mitigación: scoring por nitidez \+ dedupe

### **Riesgo: evidencia excesiva (storage)**

* mitigación: límites estrictos \+ dedupe \+ quality

### **Riesgo: paths con caracteres inválidos**

* mitigación: slug seguro para `pallet_id`

---

## **15\. Definition of Done**

2.1.D está completa cuando:

* Para cada entidad se genera un evidence pack con estructura estable.  
* Existe `evidence_index.json` consumible por API.  
* Para `NOT_COUNTABLE` hay evidencia suficiente para conteo asistido.  
* No se generan cientos/miles de imágenes por error (límites y dedupe).  
* No se agregan llamadas a Gemini.

---

## **16\. Resultado estratégico**

Después de 2.1.D:

* El sistema es auditable.  
* Se habilita el flujo humano-en-el-loop sin reprocesar videos.  
* Se reduce el costo operativo de correcciones.  
* La siguiente etapa (2.1.E) se vuelve directa: solo exponer endpoints sobre el evidence index.

---

# **Versión 2.1 — Etapa 2.1.E**

# **Assisted Counting API (Review \+ Manual Override \+ Audit)**

---

## **1\. Objetivo**

La etapa **2.1.E** expone un conjunto de endpoints para operar el flujo **human-in-the-loop** sobre los resultados del modo híbrido v2.1:

* listar entidades que requieren revisión (`NEEDS_REVIEW`, `NOT_COUNTABLE`) o están excluidas (`INVALID_STRUCTURE`),  
* acceder a la evidencia generada en 2.1.D,  
* permitir que un operador **registre** una corrección/confirmación (conteo, identificación, flags),  
* dejar trazabilidad mínima (quién, cuándo, qué cambió).

Esta etapa convierte el output del pipeline en un proceso operacional completo.

---

## **2\. Principios de diseño**

1. **No reprocesar el video** para correcciones: usar evidence packs (2.1.D).  
2. **Contrato estable**: el backend sirve “resultados \+ evidencia” con rutas/URLs.  
3. **Auditoría mínima pero real**: toda modificación queda registrada.  
4. **Idempotencia**: updates repetidos no rompen estado.  
5. **Compatibilidad**: si hoy no hay DB, soportar modo filesystem \+ `evidence_index.json`. Si hay DB, persistir.

---

## **3\. Modelo de estado (operacional)**

### **3.1 Entity states (v2.1)**

* `COUNTED`  
* `NEEDS_REVIEW`  
* `NOT_COUNTABLE`  
* `EMPTY`  
* `INVALID_STRUCTURE`  
* (nuevo estado de operación) `COUNTED_MANUAL` / `OVERRIDDEN`

### **3.2 Fuentes de verdad**

* **Fuente base**: `hybrid_report.json` \+ `evidence_index.json`  
* **Fuente de correcciones**: “review records” (DB o archivo JSON por pallet)

---

## **4\. Endpoints (contrato propuesto)**

Prefijo sugerido: `/api/v1`

### **4.1 Listar entidades de un job**

**GET** `/jobs/{job_id}/entities`

Query params:

* `status=NEEDS_REVIEW|NOT_COUNTABLE|EMPTY|INVALID_STRUCTURE|COUNTED|COUNTED_MANUAL` (opcional)  
* `entity_type=PALLET|EMPTY_PALLET|LOOSE_BOXES` (opcional)

Response:

```json
{
  "job_id": "J123",
  "mode": "hybrid_v2.1",
  "entities": [
    {
      "pallet_id": "POS-000123",
      "entity_type": "PALLET",
      "count_status": "NOT_COUNTABLE",
      "final_quantity": null,
      "position": { "barcode": null, "text": null },
      "product": { "label_text": null, "quantity": null },
      "confidence": 0.42,
      "evidence_ref": {
        "index_path": "run/evidence_index.json",
        "base_path": "run/evidence/pallet_POS-000123/"
      },
      "review": {
        "status": "PENDING|RESOLVED",
        "last_action_at": "2026-03-04T18:12:00Z",
        "last_action_by": "operator_1"
      }
    }
  ]
}
```

---

### **4.2 Obtener evidencia de una entidad**

**GET** `/jobs/{job_id}/entities/{pallet_id}/evidence`

Response:

```json
{
  "job_id": "J123",
  "pallet_id": "POS-000123",
  "entity_type": "PALLET",
  "count_status": "NOT_COUNTABLE",
  "evidence": {
    "overview": [
      {"path": "evidence/pallet_POS-000123/overview/best_000.jpg", "url": "/files/..."},
      {"path": "evidence/pallet_POS-000123/overview/best_001.jpg", "url": "/files/..."}
    ],
    "position_label_best": {"path": "...", "url": "/files/..."},
    "position_label_candidates": [],
    "product_label_best": {"path": "...", "url": "/files/..."},
    "product_label_candidates": []
  }
}
```

Nota: `url` depende de cómo sirvas archivos (static, signed URL, etc.).

---

### **4.3 Registrar conteo manual / override**

**POST** `/jobs/{job_id}/entities/{pallet_id}/review`

Body (mínimo):

```json
{
  "action": "SET_COUNT",
  "final_quantity": 15,
  "product_label_text": "INOD HALL 3L",
  "position_override": null,
  "notes": "Conteo manual por evidencia",
  "actor": "operator_1"
}
```

Acciones permitidas:

* `SET_COUNT` (define cantidad final)  
* `MARK_EMPTY` (fuerza EMPTY)  
* `MARK_INVALID_STRUCTURE` (fuerza excluido)  
* `MARK_NOT_COUNTABLE` (fuerza not countable)  
* `SET_POSITION_OVERRIDE` (si operador define ubicación)  
* `SET_PRODUCT_OVERRIDE` (si operador define producto)

Response:

```json
{
  "job_id": "J123",
  "pallet_id": "POS-000123",
  "updated": true,
  "new_status": "COUNTED_MANUAL",
  "entity": {
    "final_quantity": 15,
    "count_status": "COUNTED_MANUAL",
    "source": "manual_override"
  }
}
```

---

### **4.4 Consultar historial de auditoría**

**GET** `/jobs/{job_id}/entities/{pallet_id}/audit`

Response:

```json
{
  "job_id": "J123",
  "pallet_id": "POS-000123",
  "events": [
    {
      "timestamp": "2026-03-04T18:12:00Z",
      "actor": "operator_1",
      "action": "SET_COUNT",
      "before": {"count_status": "NOT_COUNTABLE", "final_quantity": null},
      "after": {"count_status": "COUNTED_MANUAL", "final_quantity": 15},
      "notes": "Conteo manual por evidencia"
    }
  ]
}
```

---

## **5\. Persistencia de reviews (dos modos)**

### **5.1 Modo filesystem (MVP rápido)**

Guardar en:  
`output/<job_id>/run/reviews/review_<pallet_id>.json`

Ventajas:

* rápido de implementar  
* no requiere DB

### **5.2 Modo DB (si ya estás en etapa de persistencia)**

Tablas sugeridas:

* `entity_reviews`  
* `entity_audit_events`

---

## **6\. Reglas de negocio (consistencia)**

1. Un `EMPTY_PALLET` debe tener `final_quantity = 0`.  
2. `LOOSE_BOXES` debe tener `excluded_from_inventory = true`.  
3. `SET_COUNT` solo aplica a `PALLET`.  
4. Si se hace override, el estado pasa a:  
   * `COUNTED_MANUAL` o `OVERRIDDEN`  
5. Si `pallet_id` viene por posición real, **no cambiarlo** salvo acción explícita `SET_POSITION_OVERRIDE`.

---

## **7\. Seguridad mínima (opcional en 2.1.E)**

Si todavía no tenés Auth/Roles:

* requerir `actor` en request  
* loggear IP / request\_id  
* preparar el contrato para agregar JWT más adelante

Si ya tenés auth:

* `actor` se toma del token  
* roles: `operator`, `auditor`, `admin`

---

## **8\. Integración con reporte final**

Luego de aplicar reviews, el sistema debe poder exponer:

* **reporte original** (sin overrides)  
* **reporte consolidado** (con overrides)

Propuesta:

* `hybrid_report.json` \= output del modelo  
* `hybrid_report_resolved.json` \= merge(report \+ reviews)

Endpoint:  
**GET** `/jobs/{job_id}/report?resolved=true`

---

## **9\. Cambios en código (módulos)**

Sugerencia:

* `src/api/routes/entities.py`  
  * list entities  
  * get evidence  
  * post review  
  * get audit  
* `src/review/review_store.py`  
  * filesystem store (MVP) / DB store (switch)  
* `src/review/review_merge.py`  
  * merge report \+ reviews → resolved report  
* `src/files/static_server.py` (si aplica)  
  * servir evidencia

---

## **10\. Riesgos y mitigaciones**

### **Riesgo: inconsistencias de estado**

* mitigación: validaciones por acción \+ schema

### **Riesgo: evidencia inaccesible**

* mitigación: `evidence_index.json` como contrato y health check de paths

### **Riesgo: overrides sin auditoría**

* mitigación: audit log obligatorio en cada acción

---

## **11\. Definition of Done**

2.1.E está completa cuando:

* Se pueden listar entidades por status.  
* Se puede acceder a evidencia por pallet.  
* Se puede registrar un override (conteo/manual).  
* Se registra auditoría con before/after.  
* Se puede obtener reporte consolidado `resolved`.  
* No requiere reprocesar video.

---

## **12\. Resultado estratégico**

Después de 2.1.E:

* El sistema es operable en producción con revisión humana.  
* Se reduce fricción ante casos sin etiquetas.  
* Se habilita un flujo enterprise real (auditable).  
* El siguiente paso es optimizar accuracy y automatizar más casos, sin romper operación.

---

