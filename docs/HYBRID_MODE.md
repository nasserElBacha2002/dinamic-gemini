# Modo híbrido (v2.0) — Documentación técnica

Este documento describe el flujo y la arquitectura del **modo híbrido** del sistema de inventario por video: una única llamada global a Gemini por video, selección de frames representativos y fallback visual opcional por pallet.

---

## 1. Visión general

En modo **hybrid**, el pipeline:

1. **Extrae frames representativos** del video (estrategia optimizada: filtro de blur + redundancia por hash).
2. **Envía todos esos frames en una sola llamada** a Gemini para obtener un análisis global (todos los pallets visibles).
3. **Parsea y valida** la respuesta JSON contra un schema estricto.
4. **Asigna modo de procesamiento** por pallet (label vs visual_fallback) y **opcionalmente ejecuta fallback visual** (segunda llamada Gemini con pocos frames) para pallets con baja confianza o sin etiqueta legible.
5. **Genera el reporte** (`hybrid_report.json`, `hybrid_report.csv`) y artefactos de debug.

No hay detección por frame ni tracking: el modelo ve todos los frames a la vez y devuelve una lista de pallets con atributos por pallet.

---

## 2. Flujo detallado (orden de ejecución)

```
Video → extract_representative_frames() → [frames]
       → GeminiGlobalAnalyzer.analyze_video_frames(frames)
       → JSON → validate_global_analysis_structure() → parse_global_analysis()
       → [Pallet]
       → assign_processing_mode() por pallet
       → Para cada pallet: should_trigger_fallback()?
            → Sí: VisualFallbackAnalyzer.count_visible_boxes(subset_frames) → actualiza final_quantity, confidence
       → build_hybrid_report() → write_json / write_csv
```

### 2.1 Entrada

- **Video:** ruta a archivo (ej. `.mp4`, `.MOV`).
- **Configuración relevante (env):**
  - `HYBRID_MAX_FRAMES`: máximo de frames a extraer. Vacío o `0` = sin límite (se usa un techo interno de 10000). `1..10000` = límite explícito.
  - `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`, etc.
  - Umbral de confianza para el fallback: se puede pasar por job (`confidence_threshold`); si no, se usa `DEFAULT_CONFIDENCE_THRESHOLD` (0.70).

### 2.2 Extracción de frames representativos

**Módulo:** `src/video/frames.py`  
**Función:** `extract_representative_frames(video_path, max_frames, strategy=STRATEGY_OPTIMIZED, ...)`

- **max_frames:** viene de `settings.hybrid_max_frames` (env `HYBRID_MAX_FRAMES`). Si es `None`, el pipeline usa `10000` (sin límite práctico).
- **Estrategia usada:** `STRATEGY_OPTIMIZED`.

**Optimized:**

1. **Fase A — Candidatos:** Muestreo uniforme con paso ≥ `min_gap_frames` (default 3), hasta `4 * max_frames` índices candidatos.
2. **Fase B — Filtrado:**
   - **Blur:** se descarta el frame si la varianza del Laplaciano es &lt; `blur_threshold` (default 100.0).
   - **Redundancia:** se usa dHash; si la distancia de Hamming al último frame aceptado es ≤ `hash_threshold` (default 10), se descarta.
3. **Fallback:** Si tras el filtrado quedan menos de `MIN_FRAMES_FALLBACK` (10), se rellenan con frames adicionales (muestreo uniforme) hasta al menos 10 o hasta `max_frames`.

**Salida:** `(frames: List[np.ndarray], metadata: dict)` con `metadata["fps"]` y `metadata["frame_indices"]`.

Si no se extrae ningún frame, el pipeline devuelve código de salida 1 y termina.

---

## 3. Análisis global con Gemini

**Módulo:** `src/llm/gemini_global_analyzer.py`  
**Clase:** `GeminiGlobalAnalyzer`

- **Entrada:** lista de frames (BGR, OpenCV); se convierten a PIL RGB para el cliente Gemini.
- **Una sola llamada:** `client.generate_global_analysis_raw(images, GLOBAL_PALLET_ANALYSIS_PROMPT)`.
- **Prompt:** `src/llm/global_pallet_analysis_prompt.py` — instruye a detectar todos los pallets distintos visibles, sin duplicar ni inferir pallets ocultos; salida **solo JSON** con schema fijo.

**Schema esperado (resumido):**

```json
{
  "total_pallets_detected": <int>,
  "pallets": [
    {
      "pallet_id": "<string>",
      "has_label": <bool>,
      "internal_code": "<string> | null",
      "quantity": <int> | null,
      "estimated_visible_boxes": <int> | null,
      "confidence": <float en [0, 1]>
    }
  ]
}
```

**Procesamiento de la respuesta:**

1. **Extracción de JSON:** `_strip_json_wrapper(raw)` — primero bloques ```json ... ```, si no, primer `{` hasta último `}`.
2. **Parse:** `json.loads(cleaned)` → si falla, `GlobalAnalysisParsingError`.
3. **Validación estructural:** `validate_global_analysis_structure(data)` en `src/validation/global_analysis_schema.py`:
   - Claves raíz: `total_pallets_detected`, `pallets`.
   - `total_pallets_detected == len(pallets)`.
   - Cada pallet: `pallet_id` (string), `has_label` (bool), `confidence` (float en [0,1]).
   - Si falla → `GlobalAnalysisValidationError`.

---

## 4. Parseo a modelo de dominio

**Módulo:** `src/parsing/global_analysis_parser.py`  
**Función:** `parse_global_analysis(data) -> List[Pallet]`

- Comprueba `total_pallets_detected == len(pallets)` y que no haya `pallet_id` duplicados.
- Por cada elemento de `pallets` construye un `Pallet` (`src/domain/pallet.py`):
  - `pallet_id`, `has_label`, `internal_code`, `quantity`, `estimated_visible_boxes`, `confidence`.
  - `processing_mode`, `final_quantity`, `source`, `fallback_used` quedan sin asignar aquí.

**Modelo `Pallet` (dataclass):**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| pallet_id | str | Identificador único (ej. "P1") |
| has_label | bool | Si se ve etiqueta logística |
| internal_code | Optional[str] | Código interno si hay etiqueta |
| quantity | Optional[int] | Cantidad leída de etiqueta |
| estimated_visible_boxes | Optional[int] | Cajas visibles estimadas (sin etiqueta) |
| confidence | float | Confianza en [0, 1] |
| processing_mode | Optional[str] | "label" o "visual_fallback" (asignado después) |
| final_quantity | Optional[int] | Cantidad final (label o fallback) |
| fallback_used | bool | Si se usó la llamada de fallback visual |
| source | str | "label" \| "visual_fallback" \| "unknown" |

---

## 5. Asignación de modo de procesamiento

**Módulo:** `src/decision/processing_mode.py`  
**Función:** `assign_processing_mode(pallet) -> Pallet`

- **Si** `has_label` y `internal_code` no nulo y `quantity` no nulo:
  - `processing_mode = "label"`, `source = "label"`, `final_quantity = quantity`, `fallback_used = False`.
- **En caso contrario:**
  - `processing_mode = "visual_fallback"`, `source = "visual_fallback"`, `final_quantity = estimated_visible_boxes`, `fallback_used = False`.

El resultado es una lista de pallets con modo y cantidad inicial asignados; el fallback visual puede sobrescribir `final_quantity` y `confidence` más adelante.

---

## 6. Fallback visual (opcional por pallet)

**Módulo:** `src/fallback/fallback_policy.py` + `src/fallback/visual_fallback_analyzer.py`

**Cuándo se dispara** (`should_trigger_fallback(pallet, confidence_threshold)`):

- `source == "visual_fallback"`, o
- `confidence < confidence_threshold`, o
- `has_label` y `quantity is None`.

**Qué hace:**

- Para ese pallet se toma un **subconjunto de frames** del video: `select_fallback_frames(frames, k=3)` → típicamente primer frame, central y último (determinista).
- **VisualFallbackAnalyzer.count_visible_boxes(fallback_frames):**
  - Envía hasta `FALLBACK_MAX_FRAMES` (5) frames a Gemini con un prompt corto: “Count visible boxes on the main pallet”.
  - Respuesta esperada: `{"estimated_count": <int>, "confidence": <float>}`.
  - Si la respuesta es válida, se actualiza el pallet: `final_quantity = estimated_count`, `fallback_used = True`, `confidence = confidence`.

Si la llamada de fallback falla (excepción), se registra un warning y el pallet conserva los valores anteriores (p. ej. `estimated_visible_boxes` del análisis global).

**Métricas:** el pipeline cuenta `fallback_attempts` y `fallback_success` y los incluye en el reporte (`metrics`).

---

## 7. Reporte híbrido

**Módulo:** `src/reporting/hybrid_report.py`  
**Función:** `build_hybrid_report(video_path, pallets, frames_selected, prompt_version, metrics, confidence_threshold)`

**Salida (dict):**

- **video:** `{ path, name }`
- **mode:** `"hybrid"`
- **prompt_version:** p. ej. `"global_min_v1"`
- **frames_selected:** número de frames enviados a la llamada global
- **total_pallets_detected:** `len(pallets)`
- **pallets:** lista de objetos con `pallet_id`, `has_label`, `internal_code`, `quantity`, `final_quantity`, `source`, `confidence`, `fallback_used`
- **flags:** p. ej. `low_confidence_pallets` (ids con confidence &lt; 0.50), `no_pallets_detected` si la lista está vacía
- **metrics** (opcional): `global_calls`, `fallback_attempts`, `fallback_success`, `total_calls`
- **confidence_threshold** (opcional): umbral usado para el fallback

**Escritura:**

- `write_json(run_dir / "hybrid_report.json", report)` — contrato público para integración.
- `write_csv(run_dir / "hybrid_report.csv", pallets)` — columnas: pallet_id, internal_code, final_quantity, source, confidence, fallback_used.
- `hybrid_debug.json` — artefacto de debug (mismo contenido ampliado + metadata de frames), no es contrato estable.

**Saber qué fotos se enviaron a Gemini**

- El reporte incluye **`frame_indices`**: lista de índices de frame del video que se enviaron a la llamada global (ej. `[0, 12, 24, 36, ...]`). Así sabes qué posiciones del video vio el modelo.
- **API:** `GET /api/v1/inventory/jobs/{job_id}/result` devuelve el reporte con `frame_indices` cuando existe (y `frames_selected`).
- **Guardar las imágenes enviadas:** con `DEBUG_SAVE_FRAMES=true` (env), el pipeline guarda en `output/<job_id>/run/frames_sent/` las imágenes que se enviaron a Gemini, con nombres `frame_000000.jpg`, `frame_000012.jpg`, etc. (el número es el índice del frame en el video). Podés listar esos archivos con `GET /jobs/{job_id}/artifacts` y descargarlos.

---

## 8. Configuración relevante (env)

| Variable | Default / Comportamiento | Uso en hybrid |
|----------|--------------------------|----------------|
| GEMINI_API_KEY | (requerido) | Todas las llamadas Gemini |
| GEMINI_MODEL_NAME | gemini-2.0-flash-exp | Modelo para global y fallback |
| HYBRID_MAX_FRAMES | vacío → sin límite | Máximo de frames representativos (1..10000 si se setea) |
| (confidence_threshold por job) | 0.70 si no se pasa | Umbral para disparar fallback visual |

Los parámetros de la estrategia de frames (`min_gap_frames`, `hash_threshold`, `blur_threshold`) están en código en `extract_representative_frames`; la estrategia usada es fija: `STRATEGY_OPTIMIZED`.

---

## 9. Integración con API y worker (Stage 7/8)

- El **worker** invoca `HybridInventoryPipeline().process_video(..., mode="hybrid", ...)` cuando el job tiene `mode="hybrid"`.
- Tras el éxito, escribe `hybrid_report.json` y `hybrid_report.csv` en `output/<job_id>/run/` y actualiza el job (FS y/o DB) con rutas y métricas.
- La **API** devuelve el resultado del job (desde FS o desde DB + pallet_results) con la misma forma: `mode`, `confidence_threshold`, `pallets`, `frames_selected`, `metrics`, etc.

---

## 10. Resumen de módulos

| Módulo | Responsabilidad |
|--------|-----------------|
| `src/pipeline/hybrid_inventory_pipeline.py` | Orquestación: frames → Gemini global → parse → assign_processing_mode → fallback → report |
| `src/video/frames.py` | Extracción de frames representativos (optimized / uniform) |
| `src/llm/gemini_global_analyzer.py` | Una llamada Gemini con todos los frames; extracción y validación de JSON |
| `src/llm/global_pallet_analysis_prompt.py` | Prompt y contrato JSON del análisis global |
| `src/validation/global_analysis_schema.py` | Validación estructural del JSON (tipos, claves, confidence en [0,1]) |
| `src/parsing/global_analysis_parser.py` | Dict → List[Pallet] con validaciones de negocio |
| `src/domain/pallet.py` | Modelo de datos Pallet |
| `src/decision/processing_mode.py` | Asignación label vs visual_fallback y final_quantity inicial |
| `src/fallback/fallback_policy.py` | Reglas para activar fallback por pallet |
| `src/fallback/visual_fallback_analyzer.py` | Llamada Gemini de conteo visual (pocos frames) |
| `src/reporting/hybrid_report.py` | Construcción del dict del reporte |
| `src/reporting/artifacts.py` | Escritura JSON/CSV |

Este flujo es determinista en cuanto a selección de frames y asignación de modo; la no determinismo proviene únicamente del modelo Gemini. Los umbrales de confianza y la decisión de fallback son configurables por job o por constantes (p. ej. `DEFAULT_CONFIDENCE_THRESHOLD`).
