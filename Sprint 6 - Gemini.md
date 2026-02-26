# **Plan de mejoras técnicas y plan de implementación (Adaptado — Video largo con múltiples pallets)**

## **Objetivo operativo de esta etapa (Fase 9\)**

1. **Segregación 100%**: nunca mezclar SKUs en un mismo pallet lógico.  
2. **Conteo determinista**: si la evidencia no alcanza para un conteo exacto, el sistema debe devolver **ERROR** (no estimar).  
3. **Escalabilidad en pasillo**: soportar videos de 3 minutos con **varios pallets por frame** sin explosión de costo.  
4. **Anti doble conteo**: el mismo pallet no puede contarse dos veces a lo largo del recorrido.

---

# **1\) Cambiar la unidad de procesamiento: de “frames” a “pallet tracks” (bloqueante)**

## **Problema actual**

El pipeline trata el video como un conjunto de frames y la salida puede mezclar pallets y productos. Además, si intentás multi-view sin identidad, aparece el riesgo de **duplicación** y **mezcla**.

## **Solución**

Implementar una capa de **Pallet Discovery**:

* **Detección** de pallets por frame (YOLO u otro detector simple).  
* **Tracking** (SORT/ByteTrack) para asignar un `pallet_track_id` estable.  
* A partir del tracking, el pipeline produce “**pallet events**”:  
  * `track_id`, `start_frame`, `end_frame`, `bboxes[]`

## **Entregable**

* Se construye un objeto interno: `PalletTrack { track_id, observations[] }`  
* `processing_summary.pallet_tracks_detected == #pallets únicos en el video`  
* Sin esta capa no se puede garantizar “no doble conteo”.

---

# **2\) ROI por pallet (evitar mezcla y bajar costo)**

## **Problema actual**

Si Gemini ve el frame completo con varios pallets:

* mezcla productos y pallets,  
* baja precisión,  
* sube costo innecesario por contexto irrelevante.

## **Solución**

Para cada observación de un track:

* recortar **ROI \= bbox \+ padding** (ej 10–15%)  
* normalizar resolución (`max_side 1024/1280`)  
* compresión JPEG (calidad 80–85)

## **Entregable**

* `roi_paths_by_track[track_id] -> List[path]`  
* `processing_summary.rois_generated_total`

---

# **3\) Selección de vistas por track (micro-batch multi-view, no per-frame)**

## **Problema actual**

Mandar muchas imágenes genera ruido y costo. Mandar pocas pero malas reduce evidencia y confianza.

## **Solución (mínima y efectiva)**

Para cada `track_id` seleccionar **3–5 vistas**:

* Filtrar por nitidez (Laplacian variance / blur score).  
* Elegir frames equiespaciados dentro del track (diversidad temporal).  
* Preferir frames donde el ROI sea más grande (pallet más cerca).

**Default recomendado**

* `min_views=3`, `target_views=4`, `max_views=5`

## **Entregable**

* `views_selected_total`  
* `avg_views_per_track`  
* `tracks_with_insufficient_views`

---

# **4\) Gemini: 1 request por pallet\_track (no por frame) \+ prompt multi-view anti-suma**

## **Problema actual**

El modelo puede interpretar múltiples imágenes como múltiples instancias y sumar conteos.

## **Solución**

Una sola request por `track_id` con 3–5 ROIs y un prompt que defina:

* “son vistas del MISMO pallet”  
* “no sumes por imagen”  
* “un SKU por pallet o ERROR”  
* “conteo determinista o ERROR”

## **Entregable**

* `requests_sent == pallet_tracks_detected` (aprox)  
* `frames_analyzed` deja de ser métrica principal y pasa a:  
  * `tracks_analyzed` y `views_used_per_track`

---

# **5\) Ajustar contrato minificado para producción (costo \+ control)**

## **Problema actual**

`r` obligatorio sube tokens y no aporta al output final.

## **Solución**

Crear un esquema minificado específico para “resultado por pallet\_track” con claves cortas:

* `id` (track id)  
* `s` status  
* `e` error\_code  
* `b` brand  
* `n` name  
* `q` count  
* `c` confidence  
* `v` views\_used

## **Entregable**

* Perfil `prod_track_minified` (sin razonamiento)  
* Perfil `debug_track_minified` (opcional, con reasoning)

---

# **6\) Incorporar estados/errores estructurados (determinismo real)**

## **Problema actual**

El pipeline siempre devuelve un número aunque no sea confiable.

## **Solución**

En modo estricto:

* Si no es determinista → `status=ERROR` \+ `INSUFFICIENT_EVIDENCE`  
* Si hay mezcla de SKUs → `status=ERROR` \+ `MIXED_SKUS`  
* Si `status=ERROR` → `count=null` y `confidence=0`

## **Entregable**

* Validación Pydantic estricta \+ JSON repair  
* “Fallos correctos” (no inventa)

---

# **7\) Hard constraint de segregación “un producto por pallet” aplicado post-LLM**

## **Problema actual**

Aunque el prompt lo diga, el modelo puede devolver múltiples productos para un pallet.

## **Solución**

Validador post-LLM por track:

* Si devuelve más de 1 producto distinto con confianza suficiente → ERROR `MIXED_SKUS`

## **Entregable**

* `enforce_one_product_per_pallet(track_result)` antes de consolidar/exportar.

---

# **8\) Anti doble conteo a nivel sistema (no estimación, no duplicación)**

## **Problema actual**

En un pasillo, el mismo pallet puede aparecer en varios momentos. Sin identidad (track), se puede contar dos veces.

## **Solución**

La identidad la resuelve el tracking. Además:

* si un track se pierde y reaparece, aplicar “re-ID” (fase posterior):  
  * embedding del ROI \+ clustering para fusionar tracks similares

**Sprint C o siguiente**: re-ID opcional.

## **Entregable**

* `unique_pallets_counted = number_of_tracks_after_merge` (cuando esté re-ID)  
* en Sprint A/B al menos: `1 track = 1 conteo`

---

# **9\) Ajustar I/O para modo estricto y output por track**

## **Problema actual**

Tu `FinalResult` está centrado en pallets, pero ahora el pallet\_id será `pallet_track_id` (stable).

## **Solución**

* `to_final_result()` sigue bien, pero si adoptás `status/error_code`, deberías:  
  * o bien extender `ProductEstimate/PalletEstimate` para soportar estado,  
  * o exportar un JSON adicional de auditoría por track.

**Nota técnica**

* `save_result_json` debería retornar `Path` (hoy el type dice None).

## **Entregable**

* `final_result.json` (solo OK) \+ `errors.json` (tracks en ERROR), o unificado con status.

---

# **Plan de implementación (orden sugerido)**

## **Sprint A — Identidad de pallets \+ ROI \+ micro-batch (bloqueante)**

1. Implementar detección de pallets por frame.  
2. Implementar tracking → `pallet_track_id`.  
3. ROI cropper (bbox+padding) \+ resize/compress.  
4. Selector de vistas por track (3–5).  
5. Gemini 1 request por track (prompt multi-view anti-suma).  
6. Nuevas métricas: `tracks_detected`, `tracks_analyzed`, `avg_views_per_track`.

**Resultado esperado**

* No se mezclan pallets en la request.  
* Costo pasa a depender de \#pallets, no de \#frames.  
* Se minimiza doble conteo estructuralmente.

---

## **Sprint B — Reglas duras \+ determinismo (exacto o error)**

1. Nuevo schema minificado por track con `status/error_code`.  
2. Validación post-LLM: `ONE SKU per pallet` (hard constraint).  
3. Política “determinista”: si evidencia insuficiente → ERROR.  
4. Export separado o unificado para OK/ERROR.

**Resultado esperado**

* Segregación garantizada.  
* El sistema deja de “inventar”.

---

## **Sprint C — Robustez y escalabilidad real en pasillos**

1. Re-ID (merge de tracks) para evitar duplicados cuando se pierde tracking.  
2. Mejoras de selección de vistas (diversidad angular aproximada).  
3. Optimización de costo (compresión, tamaños, caching).  
4. Observabilidad avanzada (dashboard simple por video: tracks OK vs ERROR).

**Resultado esperado**

* Menos duplicados por tracking imperfecto.  
* Mayor cobertura y menor tasa de ERROR.

---

# **Sprint A — Identidad de pallets \+ ROI \+ micro-batch (diseño técnico)**

## **Objetivo del Sprint A**

Construir un pipeline que transforme:

**Video** → **Tracks de pallets (IDs estables)** → **ROIs** → **views seleccionadas** → **1 request por track**

Sin reglas duras todavía (eso es Sprint B), pero dejando todo listo para aplicarlas.

---

# **A0) Contratos internos que necesitás (mínimos)**

### **`PalletObservation`**

* `frame_idx`  
* `timestamp_seconds`  
* `bbox` (x1,y1,x2,y2)  
* `det_conf`  
* `blur_score`  
* `roi_path` (cuando se recorta)

### **`PalletTrack`**

* `track_id`  
* `observations: List[PalletObservation]`  
* `start_frame`, `end_frame`  
* helpers:  
  * `best_views(k)` (selección)  
  * `roi_paths_for_views(k)`

### **`PalletTrackBatch`**

* `track_id`  
* `roi_paths: List[str]` (3–5)  
* `video_id`

**Criterio clave:** en Sprint A el `track_id` se convierte en tu `pallet_id` lógico.

---

# **A1) Detección de pallets por frame (base determinista)**

## **Qué detectás exactamente**

Necesitás bounding boxes de “pallet/stack”. Si no tenés un detector de pallet entrenado, hay dos caminos:

### **Opción A (rápida, MVP)**

* Detectar “cajas” (si tu YOLO ya detecta cajas)  
* Agrupar detecciones cercanas → formar un “cluster” por pallet

Esto funciona si las cajas están claramente apiladas y separadas por pallet.

### **Opción B (mejor)**

* Detector de pallets/estibas directo

Para Sprint A, **Opción A** es suficiente si ya tenés YOLO de cajas.

---

## **Output por frame**

Estructura:

* `detections = [bbox_i, conf_i]` (solo pallets, no SKUs)

---

# **A2) Tracking multi-objeto (pallet\_id estable)**

## **Por qué es obligatorio en tu caso**

Con múltiples pallets en el mismo frame:

* sin tracking no podés evitar double counting  
* no podés “agrupar vistas” del mismo pallet

## **Recomendación**

* **ByteTrack** (más robusto) o **SORT** (más simple)  
* Input: detecciones por frame  
* Output: `track_id` por bbox

## **Datos que guardás por track**

Por cada track guardás lista de observaciones con:

* `frame_idx`, `timestamp`, `bbox`, `conf`  
  y calculás luego:  
* `blur_score` del ROI correspondiente

**Criterio de aceptación**

* `track_id` debe mantenerse estable durante el tramo que el pallet está visible  
* si se pierde, se crea otro track (re-ID será Sprint C)

---

# **A3) ROI Cropper (reduce costo y elimina mezcla)**

## **Implementación recomendada**

* Por cada observación (bbox) generás ROI:  
  * padding 10–15%  
  * clamp a límites de imagen  
  * resize max\_side 1024/1280  
  * JPEG quality 80–85

## **Detalle técnico importante**

**No recortes demasiado ajustado**, porque:

* perdés bordes que sirven para contar filas/profundidad  
* el film stretch o bordes del pallet ayudan a inferir capas

Padding recomendado:

* `pad_px = 0.12 * max(width_bbox, height_bbox)`

**Criterio de aceptación**

* ROI mantiene el pallet completo (sin cortar esquinas relevantes)

---

# **A4) Score de calidad por ROI (nitidez y utilidad)**

## **Blur score (mínimo viable)**

* `blur_score = Var(Laplacian(gray(roi)))`

Guardalo por observación.

## **(Opcional) ROI size score**

* `area = (x2-x1)*(y2-y1)`  
* preferís ROIs con mayor área (pallet más cerca)

**Criterio de aceptación**

* descartás el 20–30% más borroso por track

---

# **A5) Selección de vistas por track (3–5) — determinística**

## **Objetivo**

Elegir pocas vistas, pero informativas y distintas.

### **Algoritmo recomendado (simple y sólido)**

1. Filtrar observaciones con blur por debajo de percentil 25 del track  
2. Ordenar por `frame_idx`  
3. Dividir el track en `K=target_views` segmentos temporales  
4. En cada segmento elegir la observación con:  
   * mayor blur\_score  
   * y mayor área ROI (tie-breaker)

### **Defaults**

* `min_views = 3`  
* `target_views = 4`  
* `max_views = 5`

### **Edge cases**

* track muy corto → si no llegás a `min_views`, marcás “insufficient evidence” más adelante (Sprint B)

**Criterio de aceptación**

* `views_selected_per_track` ∈ \[3..5\] para la mayoría de tracks

---

# **A6) Gemini: 1 request por track (micro-batch multi-view)**

## **Request shape**

* prompt \+ 3–5 ROIs  
* prompt **primero**, imágenes después

## **Prompt (Sprint A)**

En Sprint A todavía no hacemos “exacto o error” estricto (eso es B), pero sí:

* prohibir sumar por imagen  
* obligar a output simple por track

**Output esperado (Sprint A)**

* 1 pallet (el track)  
* 1 producto principal (aunque sea UNKNOWN)  
* 1 conteo total estimado \+ confidence \+ views\_used

En Sprint B esto se vuelve determinista con errores formales.

---

# **A7) Métricas y processing\_summary (para no ir a ciegas)**

En Sprint A cambiás la observabilidad: ya no es “frames analyzed”, es “tracks”.

## **Métricas mínimas**

* `frames_extracted`  
* `detections_total`  
* `pallet_tracks_detected`  
* `tracks_analyzed`  
* `avg_views_per_track`  
* `views_selected_total`  
* `roi_bytes_total` (aprox)  
* `requests_sent`  
* `parse_repair_rate`  
* `latency_total` y `latency_per_request_avg`

## **QA metric (muy importante)**

* % tracks con `views_selected >= 3`  
* distribución de `confidence` por track  
* varianza de conteo entre tracks similares (solo para análisis)

---

# **Definition of Done (Sprint A)**

Sprint A está listo cuando:

1. El pipeline produce `PalletTrack` estables (track\_id) para video largo con varios pallets.  
2. Para cada track se generan ROIs y se seleccionan 3–5 vistas determinísticas.  
3. Se envía **1 request por track** (no por frame).  
4. No se mezclan pallets en la request (ROIs lo garantizan).  
5. `processing_summary` refleja `tracks_detected/tracks_analyzed/views_selected_total/requests_sent`.

---

# **Riesgos conocidos (y mitigación en Sprint A)**

1. **Detector no detecta pallets bien** → agrupar cajas por cluster (MVP)  
2. **Tracker rompe IDs** → aceptable en Sprint A; re-ID es Sprint C  
3. **ROI mal recortado** → padding \+ clamp \+ QA de “ROI usable”  
4. **Vistas redundantes** → selección por segmentos temporales \+ blur

---

# **Sprint B — Reglas duras \+ determinismo (Exacto o ERROR)**

## **Objetivo del Sprint B**

1. **Regla de Oro (Segregación):**  
   `IF product_A != product_B THEN pallet_ID must be DIFFERENT`  
   → Prohibido mezclar SKUs. Si se detecta mezcla, el sistema **falla** (o marca ERROR).  
2. **Conteo determinista:**  
   Si no hay evidencia suficiente para un conteo exacto, el sistema devuelve:  
   `ERROR_INSUFFICIENT_EVIDENCE`  
   → No estimaciones “a ojo”. No “inferir profundidad” si no está confirmada.  
3. **Sistema “auditable”:**  
   Cada decisión (OK/ERROR) debe poder explicarse con métricas y validaciones, no con texto largo del LLM.

---

# **B1) Cambiar el contrato de salida: de “estimación” a “resultado con estado”**

Hoy tu `MinifiedFrameResult` / `MinifiedProduct` no soporta “ERROR”. Sprint B requiere **status** y **error\_code**.

## **Contrato propuesto (por pallet\_track)**

### **Output mínimo (prod)**

* `pallet_id`  
* `status = OK|ERROR`  
* `error_code = MIXED_SKUS|INSUFFICIENT_EVIDENCE|...`  
* `product` (brand/name) (solo si OK)  
* `count` (solo si OK)  
* `confidence` (solo si OK, y aún así la usamos solo como métrica secundaria)  
* `views_used`

En modo estricto, `confidence` no habilita “inventar”; solo sirve para observabilidad.

### **Regla estructural**

* Si `status=ERROR` → `count=null` y `confidence=0.0`

## **Entregable**

* Nuevo schema Pydantic minificado específico: `MinifiedTrackResult`  
* `response_schema` en Gemini apuntando a este schema

---

# **B2) Prompt Engineering: forzar “verificación antes de responder” sin inflar tokens**

En Sprint B, el prompt tiene que lograr dos cosas:

1. **No sumar por imagen** (son vistas del mismo pallet)  
2. **Autochequeo** para decidir si puede ser determinista

### **Técnicas aplicadas**

* Delimitadores fuertes: “ONLY JSON”  
* Reglas duras como “non-negotiable”  
* “If not sure → ERROR” explícito  
* Output con `status/error_code` (esto obliga al modelo a elegir)

Nota: evitamos pedir Chain-of-Thought largo. Pedimos “self-check” convertido en `status/error_code`, que es verificable y barato.

## **Entregable**

* Prompt Maestro B (multi-view por pallet\_track) listo para producción

---

# **B3) Validación post-LLM (hard constraints en Python)**

El prompt nunca es suficiente para garantizar 100%. Por eso Sprint B define validadores obligatorios.

## **3.1 Validador de segregación**

Si el modelo devuelve:

* múltiples productos distintos para el mismo pallet → `MIXED_SKUS`

Pero incluso si devuelve 1 producto, tu sistema debe protegerse de “variaciones”:

* Normalización fuerte (lower, sin acentos, sin puntuación)  
* `product_key = normalize(brand) + "||" + normalize(name)`

**Regla**

* Si el modelo retorna más de un `product_key` para el pallet → ERROR

## **3.2 Validador de determinismo del conteo**

Aunque devuelva `count`, si detectás señales de “estimación”:

* `views_used < min_views` → ERROR  
* `count` ausente → ERROR  
* `count` \= 0 pero hay evidencia visual fuerte (opcional) → ERROR

En Sprint B, la política es conservadora: preferimos ERROR antes que “falso OK”.

## **Entregable**

* `validate_track_result_strict(result)`  
  que devuelve OK o levanta excepción / marca ERROR.

---

# **B4) Política de “exacto o ERROR” (definición formal)**

Necesitás definir qué significa “exacto” en un pallet.

## **Definición operativa (Sprint B)**

Un conteo es determinista si:

* El patrón de apilado es visible y consistente en ≥ 2 vistas, y  
* La profundidad/capas (si aplica) se confirma en ≥ 2 vistas, y  
* No hay oclusiones relevantes (film opaco, corte de ROI), y  
* No hay mezcla de productos.

Si cualquiera falla → `INSUFFICIENT_EVIDENCE`.

### **Parámetros recomendados**

* `min_views = 3` (por pallet\_track)  
* `min_confirm_views_for_depth = 2`  
* `allow_infer_depth = False` (en modo estricto B)  
  * Solo `True` si tenés vistas lateral/oblicua claras confirmadas

---

# **B5) Manejo de errores (pipeline behavior)**

Sprint B define comportamiento: **fallar correctamente**.

Dos estrategias válidas:

## **Estrategia 1 — “Fail-fast”**

* Si un pallet falla → aborta el video completo con error  
* Útil si el inventario necesita consistencia total

## **Estrategia 2 — “Partial with error report”**

* Pallets OK se exportan  
* Pallets ERROR se exportan en `errors.json`  
* El proceso finaliza con estado “COMPLETED\_WITH\_ERRORS”

Para logística real, suele ser mejor la 2\.

---

# **B6) Observabilidad: métricas de negocio, no solo técnicas**

En Sprint B la métrica principal deja de ser “confidence” y pasa a ser:

* `tracks_ok`  
* `tracks_error_mixed_skus`  
* `tracks_error_insufficient_evidence`  
* `error_rate`  
* `avg_views_used_ok`  
* `avg_views_used_error`

Esto te permite optimizar Sprint A (más vistas/ROI mejor) sin mentirte con confidences.

---

# **Plan de implementación Sprint B (orden recomendado)**

## **Paso B.1 — Schemas nuevos (bloqueante)**

* `MinifiedTrackResult` (prod) \+ opcional `DebugTrackResult`  
* Ajustar el `response_schema` de Gemini

## **Paso B.2 — Prompt Maestro B (multi-view per track)**

* Incluir reglas duras \+ `status/error_code`  
* Eliminar reasoning obligatorio

## **Paso B.3 — Validador post-LLM**

* `enforce_one_product_per_pallet`  
* `require_min_views`  
* `reject_if_missing_fields`  
* Normalización fuerte del `product_key`

## **Paso B.4 — Política determinista**

* Implementar `StrictCountingPolicy`  
* Si no cumple → ERROR\_INSUFFICIENT\_EVIDENCE

## **Paso B.5 — Export y reporting**

* Export OK \+ Export errores  
* processing\_summary con métricas de negocio

---

# **Entregables Sprint B**

1. **Nuevo contrato JSON (prod)** con `status/error_code`  
2. **Prompt Maestro B** listo para usar  
3. **Validadores Python** (hard constraints)  
4. **Política Strict** (“exacto o ERROR”)  
5. **Reporte final**: OK \+ errores con razones

---

## **Prompt Maestro B (listo para usar)**

```
SYSTEM:
You are a strict warehouse pallet counting engine.

The images you receive are MULTIPLE VIEWS of the SAME physical pallet (same pallet_id).
You MUST NOT add counts per image. Produce ONE unified result for this pallet only.

HARD BUSINESS RULES:
1) ONE SKU PER PALLET:
   If you detect more than one distinct product/SKU on the pallet, return ERROR with error_code="MIXED_SKUS".
2) DETERMINISTIC COUNTING:
   If you cannot determine the exact count from visible evidence confirmed across views, return ERROR with error_code="INSUFFICIENT_EVIDENCE".
   Do NOT guess. Do NOT estimate hidden depth unless it is clearly visible and confirmed in at least 2 views.

OUTPUT:
Return ONLY valid JSON matching the schema. No extra text.

USER:
pallet_id: {PALLET_TRACK_ID}

You will receive 3 to 5 cropped ROI images of the SAME pallet. Ignore everything outside the pallet.

Return JSON:
{
  "pallet_id": "{PALLET_TRACK_ID}",
  "status": "OK" | "ERROR",
  "error_code": null | "MIXED_SKUS" | "INSUFFICIENT_EVIDENCE",
  "product": { "brand": null | "string", "name": "string" },
  "count": null | 0,
  "confidence": 0.0,
  "views_used": 0
}

Rules:
- If status="ERROR": count must be null and confidence must be 0.0
- If status="OK": count must be an integer >= 0
- views_used must be the number of images that contributed evidence (0..5)
Return JSON only.
```

---

Perfecto: **pHash como filtro \+ CLIP embedding solo para candidatos** es exactamente el trade-off correcto para Sprint C (costo bajo, robustez alta). Te lo dejo documentado a nivel técnico como **diseño \+ algoritmo \+ parámetros \+ entregables** para que lo puedas incorporar tal cual en tu plan.

---

# **Sprint C — Re-ID con pHash (filtro) \+ CLIP (confirmación)**

## **Objetivo**

Evitar **doble conteo** cuando el tracking se corta y un mismo pallet termina representado por **dos tracks distintos** (`track_id A` y `track_id B`).

**Solución:** fusionar tracks que corresponden al mismo pallet físico **antes** de contar con Gemini.

---

# **C1) Track Signature (huella por track)**

Para cada `PalletTrack`, construís una “firma” con 2–3 ROIs **de máxima calidad** (las mejores vistas del track).

### **1.1 Selección de ROIs para firma**

De las observaciones del track, elegís `signature_k = 2` o `3` ROIs:

Criterio:

* blur\_score alto (nítidas)  
* bbox\_area alto (pallet cercano)  
* diversidad temporal (no dos frames consecutivos)

### **1.2 Campos de la firma**

Para cada ROI seleccionado calculás:

**Coarse (barato):**

* `pHash`: perceptual hash (64-bit)  
* `bbox_centroid`: promedio (x,y) normalizado (0..1)

**Fine (caro, solo si pasa filtros):**

* `clip_embedding`: vector float (normalizado L2)

Además del track:

* `time_window`: `[t_start, t_end]`

---

# **C2) Candidate Generation (gating) — No comparar todo con todo**

Comparar todos los tracks entre sí es O(N²). Usamos gating.

## **2.1 Gate temporal**

Solo comparás tracks con proximidad temporal:

* `gap_seconds = t_start(B) - t_end(A)`  
* condición: `0 <= gap_seconds <= MAX_GAP`

Recomendación:

* `MAX_GAP = 8s` (pasillo típico)  
* si el video tiene cortes/oclusiones largas, subir a 12–15s

## **2.2 Gate espacial**

Comparás tracks con centroid similar (pallet en posición similar en pantalla):

* `dx = |cxA - cxB|`  
* `dy = |cyA - cyB|`  
* condición: `dx <= 0.20` y `dy <= 0.25` (ajustable)

Esto evita fusionar pallets distintos del mismo frame que están lejos.

---

# **C3) pHash filter (barato) — Filtro fuerte antes de CLIP**

Una vez que pasa time+space, aplicás pHash.

## **3.1 Distancia pHash**

* `hamming(phashA, phashB)`

Recomendación:

* `PHASH_MAX_DIST = 10` (con pHash 64-bit)  
* si tus ROIs varían mucho por ángulo/luz, subir a 12–14

## **3.2 Multi-ROI matching (mejor que 1-1)**

Como cada track tiene 2–3 pHash:

* calculás la distancia mínima entre cualquier par de ROIs  
* si `min_dist <= PHASH_MAX_DIST` → candidato para CLIP

Esto te protege de cambios de vista.

---

# **C4) CLIP verification (solo candidatos) — Confirmación robusta**

Para cada par candidato (A,B):

## **4.1 Similaridad coseno**

* `cos_sim = dot(embA, embB)` (asumiendo embeddings normalizados)

Como cada track tiene 2–3 embeddings:

* usás el máximo `max_sim` entre pares de embeddings

Recomendación:

* `CLIP_MIN_SIM = 0.92` (con ROIs consistentes)  
* si hay mucha variación visual: 0.90–0.91

## **4.2 Decisión**

* si `max_sim >= CLIP_MIN_SIM` → **merge**  
* sino → no merge

---

# **C5) Merge Strategy (cómo fusionar tracks)**

## **5.1 Estructura recomendada: Union-Find (DSU)**

Porque puede pasar:

* A \~ B  
* B \~ C  
  → entonces A, B y C deben fusionarse en un grupo único.

Usás un DSU:

* unís ids cuando pasan CLIP  
* al final obtenés clusters

## **5.2 Resultado del merge**

Para cada cluster:

* creás `MergedTrack(track_id="MERGED_###")`  
* concatenás observaciones ordenadas por tiempo  
* recomputás:  
  * `start/end`  
  * `best_views()` para conteo  
  * `signature` (opcional)

**Muy importante:** merge ocurre **antes** de seleccionar views para Gemini, para que el micro-batch represente el pallet completo.

---

# **C6) Entregables del módulo Re-ID**

### **Módulos nuevos sugeridos**

* `src/reid/phash.py`  
* `src/reid/clip_embedder.py`  
* `src/reid/merge_tracks.py`

### **Funciones clave**

1. `build_track_signatures(tracks) -> Dict[track_id, TrackSignature]`  
2. `generate_candidates(signatures) -> List[Pair(track_a, track_b)]`  
3. `verify_with_clip(pairs) -> List[PairConfirmed]`  
4. `merge_tracks_dsu(tracks, confirmed_pairs) -> List[MergedTrack]`

### **Métricas (processing\_summary)**

* `tracks_before_reid`  
* `tracks_after_reid`  
* `tracks_merged_count`  
* `reid_candidates_generated`  
* `clip_verifications_run`  
* `merge_clusters_sizes` (lista)

---

# **Parámetros por defecto (recomendados)**

* `signature_k = 2`  
* `MAX_GAP = 8s`  
* `dx_max = 0.20`, `dy_max = 0.25`  
* `PHASH_MAX_DIST = 10`  
* `CLIP_MIN_SIM = 0.92`

Estos son buenos defaults para depósito/pasillo típico.

---

# **Riesgos y mitigaciones**

## **Riesgo 1: false merge (fusionar pallets distintos)**

Mitigación:

* endurecer `dx/dy` gate  
* bajar `PHASH_MAX_DIST`  
* subir `CLIP_MIN_SIM` a 0.93

## **Riesgo 2: false negative (no fusionar el mismo pallet)**

Mitigación:

* subir `MAX_GAP` a 12s  
* subir `PHASH_MAX_DIST` a 12  
* bajar `CLIP_MIN_SIM` a 0.90

## **Riesgo 3: costos CLIP altos**

Mitigación:

* CLIP solo para candidatos (ya lo tenés)  
* cache embeddings por ROI (hash por bytes)

---

# **Cómo queda el flujo completo con Re-ID (resumen)**

1. Tracking → tracks  
2. Signatures (pHash \+ (candidato) CLIP)  
3. Merge tracks → merged\_tracks  
4. View selection por merged\_track (3–5)  
5. 1 request Gemini por merged\_track

Esto es exactamente lo que te asegura:

* no doble conteo por tracking roto  
* costo controlado  
* robustez real

---

Executive Summary

This document specifies the technical and implementation plan for a robust, AI-driven computer vision system designed for automated pallet and product counting in logistics environments. The core of the system is a shift from frame-based video processing to a **Pallet-Track-centric** approach, leveraging tracking and Re-Identification (Re-ID) to establish a stable physical identity for each pallet. The system prioritizes business-critical invariants—**100% SKU segregation** and **deterministic counting**—by enforcing a "Exact Count or ERROR" policy, utilizing a strict Python validation layer post-Large Language Model (LLM, i.e., Gemini) inference. The implementation is broken down into three focused Sprints: **Sprint A (Identity & Cost Control)**, **Sprint B (Determinism & Hard Rules)**, and **Sprint C (Robustness & Scalability)**.-----System Requirements1. Functional Requirements

* **Pallet Tracking:** The system must generate a stable `pallet_track_id` for every unique pallet visible in the video, regardless of video length or pallet count per frame.  
* **Micro-Batching:** The system must process each unique pallet track via a single, multi-view request to the Gemini API, using 3 to 5 selected Region of Interest (ROI) images.  
* **ROI Generation:** The system must crop and normalize ROIs (Bounding Box \+ 10–15% padding) for each pallet observation.  
* **SKU Segregation:** The system must ensure that a count is only returned for pallets containing a single product SKU. The detection of a mixed SKU must result in a `MIXED_SKUS` error.  
* **Deterministic Counting:** The system must only return a product count if there is sufficient and consistent visual evidence confirmed across multiple views. Otherwise, it must return an `INSUFFICIENT_EVIDENCE` error.  
* **Error Reporting:** The final output must include a structured report distinguishing between successfully counted pallets (`status: OK`) and failed tracks (`status: ERROR`) with a specific `error_code`.  
* **Re-Identification (Re-ID):** The system must merge broken or lost tracks of the same physical pallet using a signature-based approach (pHash filter \+ CLIP verification) before counting.

2\. Non-Functional Requirements

* **Scalability:** Must support processing videos of up to 3 minutes with multiple pallets per frame without an exponential increase in cost.  
* **Cost Control:** Processing cost must be primarily dependent on the number of unique pallet tracks, not the total number of video frames.  
* **Latency:** Latency of the counting process must be optimized through micro-batching and aggressive ROI compression/resizing (max\_side 1024/1280, JPEG quality 80–85).  
* **Availability:** The LLM integration layer must handle API timeouts and transient errors, logging failures but prioritizing local validation.

3\. Architectural Constraints

* **Core Unit:** The processing unit must change from `frame` to `pallet_track`.  
* **LLM Interface:** The Gemini API must be called once per unique pallet track, not per frame or per view.  
* **Validation Layer:** A dedicated, deterministic Python validation layer must enforce all hard business constraints post-LLM response parsing.  
* **Data Contracts:** All internal and external data transfers must use highly specific, minified JSON schemas (e.g., `MinifiedTrackResult` with short keys) to reduce LLM prompt/response token count.

4\. Business Constraints

* **Segregation:** **Non-negotiable hard constraint**: One product key per `pallet_track_id`.  
* **Determinism:** **Non-negotiable hard constraint**: Count must be exact or the system must explicitly fail with an error. No estimations allowed in strict mode.  
* **Auditability:** Every OK/ERROR decision must be traceable back to specific track data, validation rules, and views used.

5\. Failure Policies

* **Mode:** The recommended policy is **Strategy 2 — “Partial with error report”**:  
  * Pallets resulting in `OK` status are exported to `final_result.json`.  
  * Pallets resulting in `ERROR` status are exported to `errors.json` (or unified JSON with status).  
  * The video processing finalizes with a status of `COMPLETED_WITH_ERRORS`.  
* **Error States:** Must include structured error codes: `MIXED_SKUS`, `INSUFFICIENT_EVIDENCE`.

6\. Determinism Requirements

* **Counting Determinism:** A count is deemed deterministic only if the stacking pattern, layers, and depth (if applicable) are visible and consistently confirmed in $\\geq 2$ views, and no relevant occlusions or mixed products are detected.  
* **Count Value:** If `status=ERROR`, then `count` must be `null` and `confidence` must be `0.0`.  
* **Segregation Determinism:** Enforcement is a post-LLM validation step: if the LLM output suggests multiple distinct product keys for a single pallet, the track is flagged as `MIXED_SKUS`.

7\. Cost Control Policies

* **Processing Unit:** Switch primary cost driver to `requests_sent`, which should be approximately equal to `pallet_tracks_detected`.  
* **Input Optimization:** Aggressively apply ROI cropping, resizing (`max_side 1024/1280`), and JPEG compression (quality 80–85) to minimize token consumption per image.  
* **Gating (Re-ID):** Use the cheap **pHash** filter with temporal and spatial gates to severely limit the number of expensive **CLIP embedding** calculations for Re-ID.

8\. Observability Requirements

* **Core Metrics:** Primary business and technical metrics must be calculated and reported in a `processing_summary`:  
  * `tracks_detected`, `tracks_analyzed`, `tracks_ok`, `tracks_error_mixed_skus`, `tracks_error_insufficient_evidence`.  
  * `error_rate`, `avg_views_per_track`, `requests_sent`, `latency_per_request_avg`.  
* **QA Metrics:** Include `% tracks with views_selected >= 3` and distribution of `confidence` by track.  
* **Dashboard:** Must support an advanced dashboard (Sprint C) showing tracks `OK` vs `ERROR` per video.

\-----Sprint BreakdownSprint A — Identidad de pallets \+ ROI \+ micro-batch (Bloqueante)

| Section | Description |
| ----- | ----- |
| **Objective** | Establish a stable pallet identity (`pallet_track_id`) and a cost-controlled micro-batching mechanism based on ROI selection. |
| **Technical Scope** | Detection, Tracking, ROI Generation, View Selection, Gemini Micro-Batch Request. |
| **Implementation Tasks** | 1\. Implement pallet detection (Opción A: box cluster MVP). 2\. Implement multi-object tracking (ByteTrack/SORT) $\\rightarrow$ `pallet_track_id`. 3\. Implement ROI Cropper (padding 10–15%, resize 1024/1280, JPEG 80–85). 4\. Implement view selector per track (3–5 views: blur score \+ temporal diversity \+ ROI size). 5\. Implement Gemini request: 1 request per track (multi-view anti-sum prompt). |
| **Risks** | **Detector not detecting pallets well** $\\rightarrow$ *Mitigation:* Group boxes by cluster (MVP). **Tracker breaks IDs** $\\rightarrow$ *Mitigation:* Acceptable in Sprint A; Re-ID is Sprint C. **ROI mal recortado** $\\rightarrow$ *Mitigation:* Padding \+ clamp \+ QA. **Vistas redundantes** $\\rightarrow$ *Mitigation:* Selection by temporal segments \+ blur filter. |
| **Definition of Done (DoD)** | 1\. Pipeline produces stable `PalletTrack` objects for long video with multiple pallets. 2\. For each track, 3–5 deterministic ROIs are selected. 3\. **1 request per track** is sent to Gemini (not per frame). 4\. `processing_summary` reports: `tracks_detected`, `tracks_analyzed`, `views_selected_total`, `requests_sent`. |
| **Measurable KPIs** | `requests_sent` $\\approx$ `pallet_tracks_detected`. **Cost reduction**: Cost no longer dependent on `#frames`. `avg_views_per_track` $\\in \[3, 5\]$. `% tracks with views_selected >= 3` $\>$ 95%. |

Sprint B — Reglas duras \+ determinismo (Exacto o ERROR)

| Section | Description |
| ----- | ----- |
| **Objective** | Enforce hard business constraints: 100% SKU segregation and deterministic counting, shifting the system from **estimation** to **exact count or explicit error**. |
| **Technical Scope** | New output schema (`status`, `error_code`), prompt engineering for determinism, post-LLM hard constraints (Python validators), error reporting/export. |
| **Implementation Tasks** | 1\. Define and implement `MinifiedTrackResult` schema (with `status`/`error_code`). 2\. Adjust Gemini's `response_schema` to this new contract. 3\. Implement **Prompt Maestro B** (multi-view per track) including hard rules and status/error\_code. 4\. Implement post-LLM validators: `enforce_one_product_per_pallet`, `require_min_views`, strong product key normalization. 5\. Implement `StrictCountingPolicy` (e.g., if insufficient evidence $\\rightarrow$ `ERROR_INSUFFICIENT_EVIDENCE`). 6\. Implement error handling and export: separate or unified output for OK/ERROR tracks. |
| **Risks** | **LLM ignores hard rules** $\\rightarrow$ *Mitigation:* Strong post-LLM validation (hard constraints in Python). **Token explosion** $\\rightarrow$ *Mitigation:* Minified schema and removal of unnecessary reasoning from the LLM prompt. |
| **Definition of Done (DoD)** | 1\. New production JSON contract with `status`/`error_code` is in use. 2\. `Prompt Maestro B` is deployed. 3\. Python hard validators enforce ONE SKU per pallet. 4\. System explicitly fails with `ERROR` instead of estimating when evidence is insufficient (`Política Strict`). 5\. Final report includes separated or unified OK/ERROR results with reasons. |
| **Measurable KPIs** | **Result**: Segregation guaranteed. System stops “inventing”. `tracks_error_mixed_skus`, `tracks_error_insufficient_evidence` become primary monitoring metrics. `error_rate` is a key business metric. |

Sprint C — Robustez y escalabilidad real en pasillos

| Section | Description |
| ----- | ----- |
| **Objective** | Enhance system robustness and anti-double-counting capability through Re-Identification (Re-ID) to manage tracking failures in long videos/pasillos. |
| **Technical Scope** | Track Signature generation, Candidate Gating (Temporal/Spatial), pHash Filtering, CLIP Verification, Track Merge Strategy (Union-Find). |
| **Implementation Tasks** | 1\. Implement Track Signature generation (2–3 best ROIs, pHash, CLIP embedding). 2\. Implement Candidate Generation using temporal (`MAX_GAP=8s`) and spatial (`dx<=0.20`, `dy<=0.25`) gating. 3\. Implement pHash filter (Hamming distance $\\leq 10$) for coarse matching. 4\. Implement CLIP verification (Cosine similarity $\\geq 0.92$) for candidates. 5\. Implement Merge Strategy (Union-Find) to create `MergedTrack` objects *before* view selection. 6\. Implement advanced observability (dashboard, error visualization). |
| **Risks** | **False merge (fusionar pallets distintos)** $\\rightarrow$ *Mitigation:* Stricter dx/dy gate, lower `PHASH_MAX_DIST`, higher `CLIP_MIN_SIM`. **Costos CLIP altos** $\\rightarrow$ *Mitigation:* CLIP only for candidates (gating), cache embeddings. **False negative (not merging the same pallet)** $\\rightarrow$ *Mitigation:* Higher `MAX_GAP`, higher `PHASH_MAX_DIST`, lower `CLIP_MIN_SIM`. |
| **Definition of Done (DoD)** | 1\. Re-ID module successfully implemented and integrated into the pipeline pre-view selection. 2\. `tracks_before_reid` $\>$ `tracks_after_reid` for videos with tracking breaks. 3\. Final count uses `MergedTrack` objects. 4\. Advanced observability is deployed. |
| **Measurable KPIs** | `tracks_merged_count` $\>$ 0 for test videos with tracking breaks. **Result**: Fewer duplicates due to tracking imperfections. |

\-----User Stories (Agile Format)Sprint A User Stories

| \# | Role | Capability | Business Outcome |
| ----- | ----- | ----- | ----- |
| **A-1** | Warehouse Manager | Accurately detect and uniquely track every pallet | I can ensure that every single pallet is considered in the counting process. |
|  | **Acceptance Criteria:** Given a video with 10 pallets and 1 tracking loss, When the video is processed, Then the `processing_summary.pallet_tracks_detected` is 11 (10 unique \+ 1 re-created track). |  |  |
|  | **Technical Notes:** Implemented with YOLO/clustering (Opción A) and ByteTrack/SORT. |  |  |
|  | **Edge Cases:** Pallet partially occluded on entry/exit $\\rightarrow$ track may break and be re-created. |  |  |
|  | **Error Scenarios:** Tracking ID flips between two close pallets $\\rightarrow$ Must be resolved by Sprint C Re-ID. |  |  |
|  | **Observability Metrics:** `pallet_tracks_detected`, `tracks_analyzed`. |  |  |
| **A-2** | Systems Architect | Change the processing unit from frames to pallet tracks | I can decouple the processing cost from video length. |
|  | **Acceptance Criteria:** Given a 60-second video with 10 tracks, When the system processes the video, Then `requests_sent` is $\\approx 10$ and not $\\approx 1800$ (60 seconds $\\times$ 30 fps). |  |  |
|  | **Technical Notes:** `processing_summary.requests_sent == pallet_tracks_detected` (approx). |  |  |
|  | **Edge Cases:** Track is very short ( $\< 3$ views) $\\rightarrow$ No request sent; handled in Sprint B. |  |  |
|  | **Error Scenarios:** API call timeout $\\rightarrow$ Log and re-attempt; track status for this pallet remains `UNPROCESSED` in A. |  |  |
|  | **Observability Metrics:** `requests_sent`, `frames_analyzed` (secondary metric). |  |  |
| **A-3** | Video Engineer | Crop and compress ROI images for each pallet observation | I can reduce token usage and improve LLM counting focus. |
|  | **Acceptance Criteria:** Given a frame with a pallet, When the ROI Cropper is run on the bounding box, Then the output image is $\\leq 1280$ max\_side, has 10–15% padding, and has JPEG quality 80–85. |  |  |
|  | **Technical Notes:** `pad_px = 0.12 * max(width_bbox, height_bbox)`. |  |  |
|  | **Edge Cases:** Bounding box is at the image edge $\\rightarrow$ ROI must be clamped to image limits. |  |  |
|  | **Error Scenarios:** ROI is too tightly cropped (no margins) $\\rightarrow$ QA check fails; padding logic must be adjusted. |  |  |
|  | **Observability Metrics:** `roi_bytes_total`, `processing_summary.rois_generated_total`. |  |  |
| **A-4** | Data Scientist | Select the highest quality, most diverse views for counting | I can maximize the visual evidence provided to the LLM for a given cost. |
|  | **Acceptance Criteria:** Given a track with 50 observations, When the view selector runs, Then 4 views are selected: high blur score, high ROI area, and separated temporally into K=4 segments. |  |  |
|  | **Technical Notes:** Use Laplacian variance for `blur_score`. Defaults: `min_views=3`, `target_views=4`, `max_views=5`. |  |  |
|  | **Edge Cases:** All frames are blurry $\\rightarrow$ The 3-5 best frames (lowest blur rank) are still chosen, but will be flagged as `INSUFFICIENT_EVIDENCE` in Sprint B. |  |  |
|  | **Error Scenarios:** Selector returns views with poor temporal diversity $\\rightarrow$ Check equiespaciado algorithm. |  |  |
|  | **Observability Metrics:** `avg_views_per_track`, `views_selected_total`. |  |  |
| **A-5** | Integration Engineer | Send a multi-view request with an anti-sum prompt | I can prevent the LLM from double-counting products across different views of the same pallet. |
|  | **Acceptance Criteria:** Given 4 ROIs of the same pallet, When the Gemini request is sent, Then the prompt explicitly states: “son vistas del MISMO pallet” and “no sumes por imagen”. |  |  |
|  | **Technical Notes:** Request shape: Prompt first, 3–5 ROIs after. |  |  |
|  | **Edge Cases:** LLM still sums the count $\\rightarrow$ The hard constraint validator in Sprint B is required. |  |  |
|  | **Error Scenarios:** LLM returns non-JSON output $\\rightarrow$ Log `parse_repair_rate` in A7. |  |  |
|  | **Observability Metrics:** `parse_repair_rate`, `latency_per_request_avg`. |  |  |
| **A-6** | Technical Lead | View the new track-based performance metrics | I can understand the system's performance in terms of pallet coverage and view quality. |
|  | **Acceptance Criteria:** When the process finishes, Then the `processing_summary` contains `tracks_analyzed`, `avg_views_per_track`, and `% tracks with views_selected >= 3`. |  |  |
|  | **Technical Notes:** Change the primary observability focus from `frames_analyzed` to `tracks_analyzed`. |  |  |
|  | **Edge Cases:** Video contains no pallets $\\rightarrow$ `pallet_tracks_detected` should be 0\. |  |  |
|  | **Error Scenarios:** A metric is missing or null $\\rightarrow$ Check metric logging implementation. |  |  |
|  | **Observability Metrics:** All metrics in **A7** of the plan. |  |  |

Sprint B User Stories

| \# | Role | Capability | Business Outcome |
| ----- | ----- | ----- | ----- |
| **B-1** | Compliance Officer | Enforce a strict "One SKU Per Pallet" policy | I can guarantee that mixed-SKU pallets are never counted and are flagged for manual review. |
|  | **Acceptance Criteria:** Given a pallet where the LLM returns two distinct `product_key`s (even if one is low confidence), When the post-LLM validator runs, Then the track result is marked `status: ERROR` with `error_code: MIXED_SKUS`. |  |  |
|  | **Technical Notes:** Product key normalization (lower, no accents, no punctuation) is required before comparison. |  |  |
|  | **Edge Cases:** LLM returns one product but the brand/name has slight variations (e.g., "Box A" vs "Box A (v2)") $\\rightarrow$ Normalization should unify these if appropriate, or flag if distinct. |  |  |
|  | **Error Scenarios:** Validator is bypassed $\\rightarrow$ Hard constraint check must be applied to all LLM output. |  |  |
|  | **Observability Metrics:** `tracks_error_mixed_skus`. |  |  |
| **B-2** | Quality Assurance | Enforce a "Deterministic Count or Error" policy | I can trust the system's count results and avoid false positive inventory data. |
|  | **Acceptance Criteria:** Given a pallet where the stacking pattern is only visible in 1 out of 5 views, When the `StrictCountingPolicy` runs, Then the track result is marked `status: ERROR` with `error_code: INSUFFICIENT_EVIDENCE` (assuming `min_confirm_views_for_depth = 2`). |  |  |
|  | **Technical Notes:** Policy must check for minimum views and confirm depth/pattern consistency across views. |  |  |
|  | **Edge Cases:** Pallet is entirely visible from one perfect side view (no depth required) $\\rightarrow$ Policy needs to adapt or LLM must confirm "depth not applicable." **Conservative approach:** prefer `ERROR`. |  |  |
|  | **Error Scenarios:** LLM guesses a count with high confidence but evidence is low $\\rightarrow$ Post-LLM validation must override and set `count=null`, `confidence=0.0`. |  |  |
|  | **Observability Metrics:** `tracks_error_insufficient_evidence`, `error_rate`. |  |  |
| **B-3** | Backend Engineer | Use a minified, structured output contract for production | I can reduce token cost and ensure a reliable, machine-readable output. |
|  | **Acceptance Criteria:** When the Gemini request is made, Then the LLM's response adheres strictly to the `MinifiedTrackResult` JSON schema with keys like `s` (status), `e` (error\_code), `q` (count), and is validated by Pydantic. |  |  |
|  | **Technical Notes:** `MinifiedTrackResult` replaces verbose fields; `response_schema` in Gemini request is adjusted. |  |  |
|  | **Edge Cases:** LLM fails to match the schema (e.g., missing a required key) $\\rightarrow$ JSON repair logic is attempted, and `parse_repair_rate` is logged. |  |  |
|  | **Error Scenarios:** LLM returns a non-numeric count for an OK status $\\rightarrow$ Pydantic validation must fail and mark the track as `ERROR`. |  |  |
|  | **Observability Metrics:** `parse_repair_rate`, `latency_per_request_avg`. |  |  |
| **B-4** | Data Integrity Team | Clearly separate successful and failed counting results | I can easily audit and manage inventory based on reliable counts versus tracks needing human intervention. |
|  | **Acceptance Criteria:** When a video is processed with mixed OK and ERROR tracks, Then two files are exported: `final_result.json` (OK tracks only) and `errors.json` (ERROR tracks with `error_code`). |  |  |
|  | **Technical Notes:** Adopt **Strategy 2 — “Partial with error report”**. Process finalizes with `COMPLETED_WITH_ERRORS`. |  |  |
|  | **Edge Cases:** All tracks result in `OK` $\\rightarrow$ `errors.json` is empty. |  |  |
|  | **Error Scenarios:** Export process fails $\\rightarrow$ Log a critical failure and notify. |  |  |
|  | **Observability Metrics:** `tracks_ok`, `tracks_error_mixed_skus`, `tracks_error_insufficient_evidence`. |  |  |
| **B-5** | Product Owner | Force the LLM to self-check its response against the rules | I can increase the reliability of the LLM's initial output before the deterministic layer. |
|  | **Acceptance Criteria:** When a request is sent, Then the `Prompt Maestro B` contains explicit "HARD BUSINESS RULES" including "ONE SKU PER PALLET" and "DETERMINISTIC COUNTING" with "Do NOT guess" instructions. |  |  |
|  | **Technical Notes:** Prompt avoids Chain-of-Thought to save tokens, using status/error\_code choice as a self-check mechanism. |  |  |
|  | **Edge Cases:** LLM's self-check results in `OK` but post-LLM validation finds a flaw $\\rightarrow$ The Python validator must prevail (hard constraint). |  |  |
|  | **Error Scenarios:** Prompt is too long and causes request failure $\\rightarrow$ Review token count and prompt conciseness. |  |  |
|  | **Observability Metrics:** `error_rate` (indirect measure of prompt effectiveness). |  |  |
| **B-6** | Inventory Analyst | Understand the true quality of counted tracks | I can optimize warehouse processes by identifying common failure modes. |
|  | **Acceptance Criteria:** When the process finishes, Then the `processing_summary` reports `tracks_error_mixed_skus` and `tracks_error_insufficient_evidence`. |  |  |
|  | **Technical Notes:** `Confidence` is deemphasized, and structured error metrics become principal. |  |  |
|  | **Edge Cases:** A new type of error emerges (e.g., `UNSUPPORTED_PALLET_TYPE`) $\\rightarrow$ A new structured error code must be added to the schema. |  |  |
|  | **Error Scenarios:** Metrics do not reflect the actual failure counts $\\rightarrow$ Check metric calculation logic. |  |  |
|  | **Observability Metrics:** All metrics in **B6** of the plan. |  |  |

Sprint C User Stories

| \# | Role | Capability | Business Outcome |
| ----- | ----- | ----- | ----- |
| **C-1** | Operations Director | Avoid double counting of pallets that temporarily leave the frame | I can have a more accurate total count by preventing duplicated entries in my inventory system. |
|  | **Acceptance Criteria:** Given a pallet that loses track (track A ends) and reappears (track B starts) within 8 seconds, When the system runs, Then tracks A and B are successfully merged into a single `MergedTrack` *before* the Gemini counting request. |  |  |
|  | **Technical Notes:** Uses temporal gate (`MAX_GAP=8s`), spatial gate, pHash filter, and CLIP verification. |  |  |
|  | **Edge Cases:** Two similar-looking pallets pass close together $\\rightarrow$ Spatial gate (`dx/dy` constraint) and CLIP verification must prevent a **false merge**. |  |  |
|  | **Error Scenarios:** CLIP verification fails due to high cost or API error $\\rightarrow$ Merge should not occur; log as two separate tracks. |  |  |
|  | **Observability Metrics:** `tracks_before_reid`, `tracks_after_reid`, `tracks_merged_count`. |  |  |
| **C-2** | Platform Engineer | Optimize the Re-ID process for computational efficiency | I can use a high-fidelity Re-ID solution while controlling the cost of expensive CLIP embedding calls. |
|  | **Acceptance Criteria:** When Re-ID runs, Then CLIP embeddings are calculated **only** for pairs of tracks that have passed the cheap pHash filter and temporal/spatial gating. |  |  |
|  | **Technical Notes:** `CLIP_MIN_SIM = 0.92`, `PHASH_MAX_DIST = 10`. |  |  |
|  | **Edge Cases:** A pair passes pHash but is not the same pallet $\\rightarrow$ CLIP must have enough fidelity to reject the **false positive** (preventing false merge). |  |  |
|  | **Error Scenarios:** Gating logic is too restrictive $\\rightarrow$ Log `reid_candidates_generated` to check if it's too low; adjust `MAX_GAP` or `dx/dy`. |  |  |
|  | **Observability Metrics:** `reid_candidates_generated`, `clip_verifications_run` (should be much lower than `tracks_before_reid` squared). |  |  |
| **C-3** | Video Analyst | Maximize visual evidence by improving view diversity | I can improve the coverage and reduce the `INSUFFICIENT_EVIDENCE` error rate. |
|  | **Acceptance Criteria:** When a track is processed, Then the view selection algorithm incorporates an improved metric for approximate angular diversity. |  |  |
|  | **Technical Notes:** This is a planned improvement task for Sprint C (Task 2: Mejoras de selección de vistas). |  |  |
|  | **Edge Cases:** Pallet only visible from one angle $\\rightarrow$ Maximize quality and temporal spread within that limited view. |  |  |
|  | **Error Scenarios:** View selection creates redundant views $\\rightarrow$ Check diversity metric logic. |  |  |
|  | **Observability Metrics:** `error_rate`, `avg_views_used_ok`. |  |  |
| **C-4** | Site Reliability Engineer | Monitor system health and performance over time | I can proactively address issues by visualizing processing metrics and failure points. |
|  | **Acceptance Criteria:** When a video is processed, Then an advanced observability dashboard is updated to display `tracks OK vs ERROR` for that video. |  |  |
|  | **Technical Notes:** Dashboard implementation (simple view). |  |  |
|  | **Edge Cases:** High `error_rate` is sustained $\\rightarrow$ The dashboard highlights the specific video/tracks for debugging. |  |  |
|  | **Error Scenarios:** Dashboard data is out-of-sync $\\rightarrow$ Check data pipeline consistency. |  |  |
|  | **Observability Metrics:** `error_rate` (displayed prominently), `merge_clusters_sizes`. |  |  |
| **C-5** | Data Engineer | Use a robust graph-based strategy for track merging | I can ensure that transitive track relationships (A\~B, B\~C $\\rightarrow$ A\~B\~C) are correctly fused. |
|  | **Acceptance Criteria:** Given three tracks (A, B, C) that are confirmed to be the same pallet through two separate pairwise matches (A-B and B-C), When the merge strategy runs, Then A, B, and C are correctly grouped into a single cluster/`MergedTrack` using Union-Find (DSU). |  |  |
|  | **Technical Notes:** Implementation of `merge_tracks_dsu(tracks, confirmed_pairs)`. |  |  |
|  | **Edge Cases:** A merge conflict occurs (e.g., A\~B and A\~C, but B and C are distinct) $\\rightarrow$ DSU logic handles this correctly by forming one merged cluster (A, B, C). |  |  |
|  | **Error Scenarios:** DSU implementation is buggy $\\rightarrow$ Incorrect `MergedTrack` creation leading to incorrect counting. |  |  |
|  | **Observability Metrics:** `merge_clusters_sizes` (list of cluster sizes). |  |  |
| **C-6** | Inventory Manager | Receive a final count that is guaranteed not to be duplicated | I can reconcile the physical inventory with the system's count without manually checking for track breaks. |
|  | **Acceptance Criteria:** Given a video with tracking breaks, When the processing is complete, Then `unique_pallets_counted = number_of_tracks_after_merge`. |  |  |
|  | **Technical Notes:** Merge occurs *before* view selection and Gemini request, ensuring 1 request $\\rightarrow$ 1 unique pallet count. |  |  |
|  | **Edge Cases:** Re-ID is entirely disabled/failed $\\rightarrow$ The count will revert to the Sprint A/B behavior (`1 track = 1 count`). |  |  |
|  | **Error Scenarios:** Merge occurs but the `MergedTrack` is too long to select 3-5 views $\\rightarrow$ View selection needs to filter observations aggressively to meet the target. |  |  |
|  | **Observability Metrics:** `tracks_after_reid`, `unique_pallets_counted`. |  |  |

\-----Technical Validation Rules1. Segregation Enforcement (ONE SKU Per Pallet)

* **Rule:** A track result is only considered valid (`status: OK`) if it contains precisely one distinct product/SKU.  
* **Mechanism (Post-LLM Validator):**  
  1. Normalize the LLM's returned product identification fields: `product_key = normalize(brand) + "||" + normalize(name)`. Normalization includes lower-casing, removal of accents, and punctuation.  
  2. For a single pallet track, if the LLM's raw output or any subsequent interpretation returns more than one unique `product_key`, the validator must set:  
     * `status: ERROR`  
     * `error_code: MIXED_SKUS`

2\. Deterministic Counting Policy (Exacto o ERROR)

* **Rule:** A count must be exact, based on clear visual evidence confirmed across multiple views. Estimation is prohibited.  
* **Mechanism (StrictCountingPolicy):**  
  1. **View Sufficiency:** If `views_used` (from LLM output or track data) $\< \\text{min\_views}$ (recommended: 3), then set:  
     * `status: ERROR`  
     * `error_code: INSUFFICIENT_EVIDENCE`  
  2. **Visual Confirmation:** The count is *not* deterministic if:  
     * The stacking pattern is not visible or consistent in $\\geq 2$ views.  
     * Depth/layers cannot be confirmed in $\\geq 2$ views (if applicable, and `allow_infer_depth = False` in strict mode).  
     * Relevant occlusions (film opaco, ROI cut) are detected.  
  3. **LLM Trust Override:** If the LLM returns a count, but any of the conditions in (2) are violated, the validator must override the LLM's confidence and count:  
     * `status: ERROR`  
     * `count: null`  
     * `confidence: 0.0`  
     * `error_code: INSUFFICIENT_EVIDENCE`

3\. Re-ID Merge Policy

* **Objective:** Fusion of tracks A and B (where A ends and B starts) that correspond to the same physical pallet.  
* **Mechanism (Candidacy & Verification):**  
  1. **Temporal Gate:** Tracks must be compared only if the temporal gap between $t\_{\\text{end}}(A)$ and $t\_{\\text{start}}(B)$ is $0 \\le \\text{gap\_seconds} \\le \\text{MAX\_GAP}$ (default: $8s$).  
  2. **Spatial Gate:** Tracks must be compared only if their normalized `bbox_centroid` is similar: $|\\text{cx}A \- \\text{cx}B| \\le 0.20$ and $|\\text{cy}A \- \\text{cy}B| \\le 0.25$.  
  3. **Coarse Filter (pHash):** A track pair that passes both gates is a candidate if the minimum Hamming distance between any pair of their signature ROIs (2–3 views per track) is $\\le \\text{PHASH\_MAX\_DIST}$ (default: 10).  
  4. **Fine Verification (CLIP):** The final merge decision is made if the maximum Cosine Similarity between any pair of their signature CLIP embeddings is $\\ge \\text{CLIP\_MIN\_SIM}$ (default: 0.92).  
  5. **Fusion Strategy:** Confirmed pairs are merged into a single `MergedTrack` using a **Union-Find (DSU)** data structure to handle transitive relations (A $\\sim$ B $\\sim$ C).

4\. Error State Handling

| Condition | status | error\_code | count | confidence |
| ----- | ----- | ----- | ----- | ----- |
| Valid, Deterministic Count | OK | null | integer $\\ge 0$ | $0.0 \< \\text{float} \\le 1.0$ |
| Segregation Rule Violated | ERROR | MIXED\_SKUS | null | 0.0 |
| Insufficient Visual Evidence | ERROR | INSUFFICIENT\_EVIDENCE | null | 0.0 |
| LLM Response Parsing Failed | ERROR | PARSE\_FAILURE (implicit) | null | 0.0 |

* **Export:** OK and ERROR tracks are exported separately to support the **Partial with error report** failure policy.

5\. Data Validation Strategy (Post-LLM)

* **Type Checking:** Use **Pydantic** validation on the minified JSON schema (`MinifiedTrackResult`) to ensure strict data types (e.g., `count` is an integer, `confidence` is a float).  
* **Field Presence:** `reject_if_missing_fields` (e.g., `pallet_id`, `status` must be present).  
* **Conditional Logic:** The validator must check structural rules:  
  * If `status: ERROR`, then `count` *must* be `null` and `confidence` *must* be `0.0`.  
  * If `status: OK`, then `count` *must* be an integer $\\ge 0$.

6\. JSON Schema Validation Strategy

* **Contract:** The external-facing LLM contract uses a minified JSON schema to reduce token usage and enforce a rigid structure.  
* **LLM Role:** The LLM is instructed to return **ONLY valid JSON** matching the schema, with no extra text, reinforcing the machine-readable output.

\-----Architecture OverviewProcessing Stages and Data Contracts

The system is structured as a sequential pipeline with clear data contracts between stages, maximizing deterministic logic where possible.

| Stage | AI/ML Use | Deterministic Logic Use | Input Contract | Output Contract |
| ----- | ----- | ----- | ----- | ----- |
| **1\. Video Ingestion** | None | Frame extraction, timestamping. | Video File | List of Video Frames |
| **2\. Pallet Discovery** | YOLO/Detector | Aggregation of box detections into a single Pallet BBox (Opción A). | Video Frames | List of BBox Detections per Frame |
| **3\. Tracking** | None | Multi-Object Tracking (SORT/ByteTrack). | BBox Detections | `PalletTrack` object (List of `PalletObservation` objects). |
| **4\. Re-ID (Sprint C)** | CLIP Embedding (Expensive) | Temporal/Spatial Gating, pHash Filtering, Union-Find (DSU) Merge. | List of `PalletTrack` objects | List of `MergedTrack` objects |
| **5\. ROI Generation & View Selection** | None | Cropping/Resizing/Compression, Blur Score Calc, Selection Algorithm (Temporal Segments, Max Blur/Area). | `PalletObservation` data | `PalletTrackBatch` (3–5 ROIs \+ `track_id`) |
| **6\. LLM Counting** | Gemini API (Vision Model) | None (LLM inference is non-deterministic). | `PalletTrackBatch` \+ Prompt Maestro B | Raw `MinifiedTrackResult` JSON |
| **7\. Validation & Export** | None | Pydantic validation, Segregation Enforcement, Deterministic Counting Policy, Error State Handling. | Raw `MinifiedTrackResult` | `final_result.json` (OK tracks), `errors.json` (ERROR tracks) |

Failure Boundaries

* **Stage 1-5 (Pre-LLM):** Failures (e.g., ROI cropping error, Re-ID API error) result in the affected track being flagged early. This track is then either skipped or sent to the LLM with insufficient views, leading to an `INSUFFICIENT_EVIDENCE` error in Stage 7\.  
* **Stage 6 (LLM):** LLM response failures (timeout, non-JSON output) are contained and logged as a parsing error, which Stage 7 converts to an `ERROR` status for the track.  
* **Stage 7 (Post-LLM):** This is the **final failure boundary**. This deterministic logic cannot be overridden and enforces all business invariants. If an invariant is violated, the track result is immediately converted to an `ERROR` state (e.g., `MIXED_SKUS`).

Where AI is Used and Where Deterministic Logic is Enforced

| Component | Function | Enforcement Type |
| ----- | ----- | ----- |
| **Pallet Detector** | Initial bounding box generation. | AI (Vision) |
| **ROI Cropper** | Cropping logic, padding, compression. | Deterministic Logic (Python) |
| **View Selector** | Filtering based on blur score, temporal diversity. | Deterministic Logic (Python) |
| **CLIP Embedder** | High-fidelity Re-ID verification. | AI (Vision/Feature Extraction) |
| **Gemini API** | Product identification and counting. | AI (LLM Inference) |
| **Prompt Maestro B** | Guides LLM to self-check and use structured output. | AI (Prompt Engineering) |
| **DSU Merge** | Fusion of track clusters. | Deterministic Logic (Algorithm) |
| **Segregation Validator** | Enforce ONE SKU per pallet. | Deterministic Logic (Python Hard Constraint) |
| **StrictCountingPolicy** | Enforce Exact Count or ERROR. | Deterministic Logic (Python Hard Constraint) |
| **JSON Schema Validator** | Enforce data contract integrity. | Deterministic Logic (Pydantic) |

