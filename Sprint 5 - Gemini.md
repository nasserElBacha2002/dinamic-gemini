## **Documento de requerimientos — Sistema de inventario por video \+ Gemini (Python)**

### **1\) Objetivo**

Construir un sistema en Python que reciba un **video** (depósito / racks / pallets), extraiga **fotogramas** (frames) con una estrategia configurable y use la **API de Gemini** para:

* **contar cajas por pallet** y **distinguir productos** cuando sea posible,  
* devolviendo una salida **simple y parseable** en **JSON** (pallets → productos → cantidad estimada \+ confianza).

---

### **2\) Alcance del MVP**

Incluye:

* Ingesta de video (archivo local inicialmente).  
* Extracción de fotogramas configurable.  
* Pipeline de envío a Gemini con prompts “production-oriented”.  
* Agregación de resultados por pallet/producto.  
* Export de resultados JSON y logs.

No incluye (por ahora):

* Entrenamiento de modelos propios.  
* Tracking multi-objeto avanzado (aunque se deja preparado).  
* Integración directa a WMS/ERP (solo export).  
* UI web (solo CLI).

---

### **3\) Actores / Roles**

* **Operador**: ejecuta el programa con un video y obtiene un reporte JSON.  
* **Sistema**: procesa video, consulta Gemini, consolida resultados.  
* **Auditor/Analista**: revisa resultados y logs (opcional).

---

### **4\) Entradas y salidas**

#### **4.1 Entrada**

* Archivo de video (`.mp4`, `.mov`, etc.)  
* Parámetros de ejecución (CLI o config):  
  * `fps_sampling` o `every_n_frames`  
  * `max_frames`  
  * `roi` opcional (recorte del área útil)  
  * `quality` / `resize`  
  * `batch_size`  
  * `prompt_profile` (pallet\_counting\_simple, etc.)

#### **4.2 Salidas (obligatorias)**

* `result.json` con estructura mínima:

```json
{
  "video_id": "XYZ",
  "pallets": [
    {
      "pallet_id": "PALLET_001",
      "products": [
        { "brand": "Cremigal", "product": "Leche UAT Entera 12x1L", "estimated_boxes": 84, "confidence": 0.93 }
      ]
    }
  ]
}
```

#### **4.3 Salidas (opcionales)**

* Frames guardados en `output/<video_id>/frames/`  
* “Contact sheet” o preview de frames seleccionados  
* `run.log` con métricas, tiempos, errores, tokens (si se puede)

---

### **5\) Requerimientos funcionales (RF)**

**RF-01 — Ingesta de video**  
El sistema debe aceptar un video local y validar:

* existencia,  
* formato soportado,  
* duración, fps y resolución.

**RF-02 — Extracción de fotogramas**  
El sistema debe generar frames con una estrategia configurable:

* por FPS objetivo (ej: 1 fps),  
* por salto de frames (ej: cada 30),  
* por escena/cambio (opcional futuro).

**RF-03 — Normalización de imagen**  
Cada frame debe poder:

* redimensionarse,  
* comprimirse,  
* recortarse (ROI),  
  para controlar costo y mejorar señal.

**RF-04 — Selección inteligente de frames (MVP simple)**  
Debe permitir limitar la cantidad de frames enviados a Gemini:

* `max_frames` y/o muestreo uniforme.

**RF-05 — Envío a Gemini**  
El sistema debe integrar la API de Gemini y enviar:

* prompt “fijo” \+ imágenes (frames),  
* con control de reintentos y timeouts.

**RF-06 — Prompt “simple output”**  
Debe usar un prompt que obligue salida **JSON mínima**:

* pallet\_id  
* lista de productos  
* estimated\_boxes  
* confidence  
  Sin texto adicional.

**RF-07 — Parseo robusto de respuesta**  
El sistema debe:

* validar que la respuesta sea JSON,  
* si no lo es, reintentar con un prompt de “repair JSON”.

**RF-08 — Consolidación multi-frame**  
Si un pallet aparece en múltiples frames, el sistema debe:

* agrupar resultados por pallet,  
* evitar duplicados,  
* combinar conteos y ajustar confianza (reglas definidas).

**RF-09 — Export de resultados**  
Debe guardar:

* `result.json`  
* y un resumen en consola (mínimo).

**RF-10 — Modo “debug”**  
Debe poder guardar:

* frames enviados,  
* request/response de Gemini (redactando secretos),  
* para auditar.

---

### **6\) Requerimientos no funcionales (RNF)**

**RNF-01 — Escalabilidad de costo**  
Debe minimizar costo:

* compresión,  
* límite de frames,  
* batching,  
* profiles de prompt.

**RNF-02 — Reproducibilidad**  
Con el mismo video y misma config, se debe obtener:

* mismos frames seleccionados,  
* output consistente (dentro de variabilidad del modelo).

**RNF-03 — Observabilidad**  
Logs con:

* tiempos por etapa,  
* cantidad de frames,  
* tamaño total enviado,  
* errores y reintentos,  
* ID de corrida.

**RNF-04 — Seguridad**

* API key solo por variables de entorno (`GEMINI_API_KEY`)  
* no debe persistirse en logs.

**RNF-05 — Portabilidad**  
Debe correr en:

* macOS / Linux (primario),  
* Windows (secundario).

**RNF-06 — Robustez**

* manejo de videos corruptos,  
* frames vacíos,  
* respuestas no parseables,  
* rate limits.

---

### **7\) Arquitectura propuesta (módulos Python)**

**7.1 Estructura de carpetas**

* `src/`  
  * `video/` (lectura \+ extracción)  
  * `frames/` (sampling \+ preprocess)  
  * `llm/` (cliente Gemini \+ prompts)  
  * `postprocess/` (parser \+ merge)  
  * `schemas/` (modelos Pydantic)  
  * `cli.py` (entrada principal)  
* `output/`  
* `configs/`

**7.2 Flujo**

1. VideoLoader → 2\) FrameExtractor → 3\) Preprocess →  
2. GeminiClient(prompt+frames) → 5\) JSONParser →  
3. Merger → 7\) Export.

---

### **8\) Reglas mínimas de consolidación (MVP)**

* Si Gemini devuelve el mismo producto en varios frames:  
  * usar **mediana** o **máximo confiable** (configurable).  
* Si productos son ambiguos:  
  * mantener entradas separadas (no fusionar).  
* Confianza final:  
  * promedio ponderado por cantidad de evidencias (frame\_count).

---

### **9\) Interfaz de ejecución (CLI)**

Ejemplo deseado:

```shell
python -m src.cli \
  --video data/VID_001.mp4 \
  --fps 1 \
  --max-frames 20 \
  --resize 1280 \
  --profile pallet_count_simple \
  --output output/
```

---

### **10\) Criterios de aceptación (Definition of Done)**

* Dado un video de depósito:  
  * genera frames  
  * consulta Gemini sin romper formato  
  * devuelve un `result.json` parseable  
  * contiene pallets y conteos con confianza  
  * logs disponibles  
* Si Gemini responde texto:  
  * el sistema reintenta y termina con JSON válido.

---

### **11\) Riesgos y limitaciones (a considerar)**

* Variabilidad del conteo con visión parcial.  
* Oclusiones (film stretch, racks, sombras).  
* Identificación de producto si no hay texto legible.  
* Doble conteo si frames muestran pallets distintos o repetidos sin tracking.

---

Perfecto. Vamos a armar un **Documento Técnico formal**, pensado como si lo fueras a presentar internamente en Dinamic Systems o incluso a un partner logístico.

Lo estructuro estilo **Technical Specification \+ Architecture Design Document (ADD)**.

---

# **📄 Documento Técnico**

# **Sistema de Conteo de Inventario por Video**

## **Integración Python \+ Gemini API**

---

# **1\. Visión General**

## **1.1 Objetivo Técnico**

Diseñar e implementar un sistema en Python capaz de:

1. Recibir un video de depósito.  
2. Extraer fotogramas estratégicamente.  
3. Enviar imágenes seleccionadas a la API de Gemini.  
4. Obtener estimaciones de cantidad de cajas por pallet.  
5. Consolidar resultados en un JSON estructurado listo para integración futura con sistemas ERP/WMS.

---

## **1.2 Problema que Resuelve**

En depósitos:

* Los pallets contienen cajas apiladas.  
* El conteo manual es lento y propenso a error.  
* No existe sistema automático liviano para validar stock visualmente.

El sistema permite:

* Conteo visual automático.  
* Auditoría rápida.  
* Validación de inventario sin escaneo unidad por unidad.

---

# **2\. Arquitectura General del Sistema**

## **2.1 Diagrama lógico del flujo**

```
Video Input
   ↓
Frame Extraction
   ↓
Frame Selection & Preprocessing
   ↓
Gemini API (Vision)
   ↓
JSON Validation & Parsing
   ↓
Result Aggregation
   ↓
Final result.json
```

---

# **3\. Componentes Técnicos**

---

## **3.1 Video Ingestion Module**

Responsabilidades:

* Validar archivo.  
* Extraer metadata (fps, duración, resolución).  
* Manejar errores de formato.

Tecnología:

* OpenCV (`cv2`)  
* ffmpeg (opcional backend)

Input:

* path al video

Output:

* objeto `VideoMetadata`

---

## **3.2 Frame Extraction Module**

Responsabilidades:

* Generar frames según estrategia configurable.  
* Controlar densidad de muestreo.

Estrategias soportadas:

* Muestreo por FPS objetivo (ej: 1 fps).  
* Cada N frames.  
* Límite máximo de frames.  
* Futuro: detección de cambios de escena.

Output:

* Lista de imágenes en memoria o guardadas temporalmente.

---

## **3.3 Frame Preprocessing Module**

Responsabilidades:

* Redimensionar imágenes.  
* Comprimir.  
* Aplicar ROI (opcional).  
* Filtrar imágenes borrosas (opcional futuro).

Motivación:

* Reducir costo API.  
* Mejorar señal.

---

## **3.4 Gemini Integration Module**

Responsabilidades:

* Construir request.  
* Adjuntar imágenes.  
* Aplicar prompt profile.  
* Manejar reintentos.  
* Validar JSON de salida.

Requerimientos:

* API key por variable de entorno.  
* Manejo de rate limits.  
* Timeout configurable.

---

## **3.5 Prompt Profiles**

Se define un sistema de perfiles de prompt.

Ejemplo:

* `pallet_count_simple`  
* `multi_pallet_detection`  
* `strict_visible_only`  
* `pattern_inferred`

Cada perfil define:

* System prompt  
* User prompt  
* Esquema esperado de salida

---

## **3.6 JSON Parser & Validator**

Responsabilidades:

* Validar estructura JSON.  
* Verificar campos obligatorios.  
* Corregir JSON malformado mediante retry.

Validación mediante:

* Pydantic models  
* JSON schema

---

## **3.7 Result Aggregation Module**

Responsabilidades:

* Agrupar resultados por pallet.  
* Evitar doble conteo.  
* Calcular:  
  * promedio  
  * mediana  
  * máximo confiable  
* Ajustar confianza final.

Estrategia inicial (MVP):

* Usar mediana de `estimated_boxes` por pallet.  
* Confianza \= promedio ponderado.

---

# **4\. Esquemas de Datos**

---

## **4.1 Resultado Final (Contrato del Sistema)**

```json
{
  "video_id": "VID_001",
  "processing_summary": {
    "frames_extracted": 25,
    "frames_sent_to_llm": 10,
    "processing_time_seconds": 18.3
  },
  "pallets": [
    {
      "pallet_id": "PALLET_001",
      "products": [
        {
          "brand": "Cremigal",
          "product": "Leche UAT Entera 12x1L",
          "estimated_boxes": 72,
          "confidence": 0.88,
          "evidence_frames": 6
        }
      ]
    }
  ]
}
```

---

# **5\. Historias de Usuario**

---

## **HU-01 — Conteo básico**

Como operador  
Quiero pasar un video  
Para obtener un JSON con cantidad de cajas por pallet.

Criterios:

* Se genera result.json  
* Contiene pallets  
* Tiene estimated\_boxes y confidence

---

## **HU-02 — Control de costos**

Como administrador  
Quiero limitar la cantidad de frames enviados  
Para controlar el costo del uso de API.

Criterios:

* Parámetro max\_frames configurable  
* Reporte muestra cuántos frames se enviaron

---

## **HU-03 — Auditoría**

Como auditor  
Quiero poder revisar qué imágenes fueron enviadas  
Para validar el conteo.

Criterios:

* Modo debug guarda frames.  
* Guarda response raw.

---

# **6\. Requerimientos No Funcionales**

---

## **6.1 Performance**

* Video de hasta 2 minutos debe procesarse en menos de 60 segundos (dependiente de API).  
* Extracción de frames no debe exceder 20% del tiempo total.

---

## **6.2 Escalabilidad**

Diseño modular permite:

* Reemplazar Gemini por otro modelo.  
* Integrar YOLO previo.  
* Integrar tracking.  
* Migrar a arquitectura cloud.

---

## **6.3 Seguridad**

* API keys solo en variables de entorno.  
* No persistir claves en logs.  
* Sanitizar outputs.

---

## **6.4 Observabilidad**

Se debe registrar:

* ID de ejecución  
* Frames enviados  
* Tiempo por etapa  
* Errores  
* Reintentos

---

# **7\. Roadmap Técnico**

---

## **Fase 1 — MVP funcional**

* Video → Frames  
* Gemini simple  
* JSON final  
* Sin consolidación compleja

---

## **Fase 2 — Optimización**

* Frame filtering inteligente  
* Consolidación avanzada  
* Retry JSON repair  
* Rango de incertidumbre

---

## **Fase 3 — Híbrido**

* YOLO para detección de pallets  
* Gemini para conteo estructural  
* Tracking multi-frame

---

## **Fase 4 — Producción**

* Servicio REST  
* Integración con ERP  
* Modo batch  
* Control de costos dinámico  
* Métricas y dashboard

---

# **8\. Riesgos Técnicos Identificados**

* Variabilidad del modelo en conteo.  
* Oclusiones por film stretch.  
* Pallets parcialmente visibles.  
* Mezcla de productos en misma tarima.  
* Conteo duplicado por múltiples vistas.

Mitigación:

* Consolidación estadística.  
* Restricción de prompt.  
* Validación estructural.  
* Threshold de confianza.

---

# **9\. Criterios de Éxito del MVP**

Se considera exitoso si:

* Error promedio \< 10% en 20 videos con ground truth.  
* Output consistente entre ejecuciones.  
* JSON válido 100% de las veces.  
* Costo por video aceptable.

---

# **10\. Extensiones Futuras**

* Integración con drones.  
* Conteo 3D multi-ángulo.  
* Detección de huecos.  
* Identificación SKU exacto.  
* Edge inference híbrido.  
* Sistema de aprendizaje continuo.

---

## **1\) Modelos Pydantic (contratos “production-ready”)**

Asumo **Pydantic v2**.

```py
# src/models/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal, Tuple
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

# ----------------------------
# Helpers
# ----------------------------
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

# ----------------------------
# Minimal models for JSON API Output (Cost optimization)
# ----------------------------
class MinifiedProduct(BaseModel):
    """Modelo ultracompacto SOLO para el JSON de salida de Gemini."""
    model_config = ConfigDict(extra="forbid")

    # Claves minificadas (n: product, q: estimated_boxes, c: confidence, b: brand)
    n: str = Field(..., description="Nombre o descripción del producto.")
    q: int = Field(..., ge=0, description="Cantidad estimada de cajas.")
    c: float = Field(..., ge=0, le=1, description="Nivel de confianza (0 a 1).")
    b: Optional[str] = Field(None, description="Marca del producto (opcional).")

    @field_validator("c")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        return clamp01(v)

class MinifiedPallet(BaseModel):
    """Modelo ultracompacto para un Pallet SOLO para la salida de Gemini."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Identificador único del pallet.")
    p: List[MinifiedProduct] = Field(..., description="Lista de productos en el pallet.")

class MinifiedFrameResult(BaseModel):
    """El objeto JSON completo que Gemini debe devolver para un frame."""
    model_config = ConfigDict(extra="forbid")

    pallets: List[MinifiedPallet] = Field(..., description="Lista de pallets detectados.")


# ----------------------------
# Core metadata
# ----------------------------
class VideoMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_id: str
    file_path: str
    duration_seconds: float = Field(..., gt=0)
    fps: float = Field(..., gt=0)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)


class FrameRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_idx: int = Field(..., ge=0)
    timestamp_seconds: float = Field(..., ge=0)
    image_path: Optional[str] = None  # si guardás frames a disco
    width: Optional[int] = Field(default=None, gt=0)
    height: Optional[int] = Field(default=None, gt=0)


# ----------------------------
# Minimal output you want (simple)
# ----------------------------
class ProductEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: Optional[str] = None
    product: str
    estimated_boxes: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)

    @field_validator("confidence")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        return clamp01(v)


class PalletEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pallet_id: str
    products: List[ProductEstimate]


class FinalResult(BaseModel):
    """
    Este es el contrato FINAL del sistema: simple, barato, directo.
    """
    model_config = ConfigDict(extra="forbid")

    video_id: str
    pallets: List[PalletEstimate]
    # opcional pero útil para debug/observabilidad
    processing_summary: Optional[Dict[str, Any]] = None


# ----------------------------
# Detailed internal LLM outputs (para consolidación)
# ----------------------------
class LLMProductObservation(BaseModel):
    """
    Lo que el LLM “cree” ver en un frame para un producto.
    """
    model_config = ConfigDict(extra="forbid")

    product: str
    brand: Optional[str] = None
    estimated_boxes: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)

    @field_validator("confidence")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        return clamp01(v)


class LLMPalletObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pallet_id: str
    products: List[LLMProductObservation]


class LLMFrameResult(BaseModel):
    """
    Resultado del LLM para 1 frame.
    """
    model_config = ConfigDict(extra="forbid")

    frame: FrameRef
    pallets: List[LLMPalletObservation]
    raw_text: Optional[str] = None  # respuesta cruda del LLM (debug)
    model_name: Optional[str] = None


# ----------------------------
# Consolidation outputs (auditables)
# ----------------------------
class ConsolidationStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_observations: int = Field(..., ge=0)
    min_est: Optional[int] = None
    max_est: Optional[int] = None
    median_est: Optional[float] = None
    mad: Optional[float] = None  # median absolute deviation


class ConsolidatedProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str
    brand: Optional[str] = None
    estimated_boxes: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)

    evidence_frames: int = Field(..., ge=0)
    stats: Optional[ConsolidationStats] = None

    @field_validator("confidence")
    @classmethod
    def _conf_01(cls, v: float) -> float:
        return clamp01(v)


class ConsolidatedPallet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pallet_id: str
    products: List[ConsolidatedProduct]


class ConsolidatedResult(BaseModel):
    """
    Resultado consolidado (interno). Luego podés mapearlo a FinalResult simple.
    """
    model_config = ConfigDict(extra="forbid")

    video_id: str
    pallets: List[ConsolidatedPallet]
```

**Idea clave:**

* Tu **API pública** puede ser `FinalResult` (simple: pallet \-\> productos \-\> cantidad \+ confianza).  
* Tu **pipeline interno** usa `LLMFrameResult` y `ConsolidatedResult` para consolidar y auditar sin inflar el output final.

---

## **2\) Estrategia matemática de consolidación (robusta \+ barata)**

El problema real: el LLM puede variar entre frames, y a veces “se inventa” profundidad o confunde productos.

### **2.1 Agrupación**

Agrupás observaciones por:

* `pallet_id`  
* `product_key = normalize(brand + product)` (o `product` solo si no hay brand)

Por cada grupo tenés una lista de tuplas:

* `x_i = estimated_boxes`  
* `c_i = confidence` (0..1)  
* `frame_idx / timestamp`

### **2.2 Limpieza de outliers (MAD)**

Usás **Median Absolute Deviation** porque es robusto:

1. `m = median(x)`  
2. `MAD = median(|x_i - m|)`  
3. Si `MAD == 0`, no filtrás (o filtrás por igualdad a `m`)  
4. Si `MAD > 0`, definís inliers:  
   * `|x_i - m| <= k * MAD` (k típico: 2.5 o 3.0)

Esto te elimina frames raros donde el LLM deliró.

### **2.3 Estimación final (mediana ponderada o mediana simple)**

Para conteos discretos, la **mediana** suele ser lo más estable.

* `x_hat = round(median(inliers))`

Opcional (más fino): **trimmed mean** (recortás 10% extremos) si hay muchos datos.

### **2.4 Confianza final (no inventada, penaliza inestabilidad)**

Querés una confianza que baje si los frames discrepan o hay poca evidencia.

Propuesta simple y efectiva:

* `conf_mean = mean(c_i de inliers)`  
* `stability_factor = exp(- (MAD / max(1, m)) )`  
  * Si MAD alto vs conteo, baja la confianza.  
* `coverage_factor = clamp01(log(1 + n_inliers) / log(1 + N_target))`  
  * N\_target típico 6–10 frames.  
* `conf_final = clamp01(conf_mean * stability_factor * coverage_factor)`

### **2.5 Evidencia**

* `evidence_frames = n_inliers`

### **2.6 Regla para “producto dudoso”**

Si `evidence_frames < 2` o `conf_final < 0.35`, podés:

* mantenerlo igual pero con baja confianza, o  
* filtrarlo del output final (dependiendo del caso de negocio)

---

## **3\) Esqueleto del proyecto Python (estructura \+ CLI)**

### **3.1 Estructura de carpetas**

```
inventory_video_counter/
  pyproject.toml
  README.md
  .env.example
  src/
    app.py
    config.py
    models/
      schemas.py
    video/
      ingest.py
      frames.py
    preprocess/
      image_ops.py
      selectors.py
    llm/
      gemini_client.py
      prompts.py
    consolidate/
      consolidate.py
      normalize.py
    io/
      outputs.py
      logging.py
  tests/
    test_consolidate.py
```

### **3.2 Configuración**

```py
# src/config.py
from pydantic import BaseModel, Field
import os

class Settings(BaseModel):
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    max_frames_to_send: int = 10
    extract_fps: float = 1.0  # frames por segundo para extracción
    resize_max_side: int = 1280
    output_dir: str = "output"
    debug_save_frames: bool = False

def load_settings() -> Settings:
    return Settings()
```

### **3.3 Frame extraction (OpenCV)**

```py
# src/video/frames.py
import cv2
from typing import List
from src.models.schemas import FrameRef

def extract_frames(video_path: str, target_fps: float) -> List[FrameRef]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / target_fps)))

    frames: List[FrameRef] = []
    idx = 0
    out_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if idx % step == 0:
            ts = idx / fps
            h, w = frame.shape[:2]
            frames.append(FrameRef(frame_idx=idx, timestamp_seconds=ts, width=w, height=h))
            out_idx += 1

        idx += 1

    cap.release()
    return frames
```

Nota: este extractor devuelve solo referencias; en el MVP podés guardar/leer frames, o tenerlos en RAM. Para costo y simplicidad, suele convenir: **extraer → seleccionar → guardar solo los seleccionados**.

### **3.4 Prompt minimal (lo que vos pediste: simple)**

```py

# src/llm/prompts.py
from typing import Final

# 1. Nuevo System Prompt: Define el rol y la tarea lógica.
SYSTEM_PROMPT_PALLET_COUNT: Final[str] = """\
Eres un experto en visión por computadora para inventarios logísticos.
Tu única tarea es analizar la imagen de un depósito o rack y devolver la detección y conteo de cajas por pallet en el formato JSON estrictamente requerido por el esquema.
Debes identificar el pallet, los productos que contiene (si son distinguibles) y estimar la cantidad de cajas con un nivel de confianza (0.0 a 1.0).
No incluyas explicaciones, texto adicional, ni formato Markdown fuera del objeto JSON.
"""

# 2. User Prompt: Es la instrucción que acompaña a la imagen.
USER_PROMPT_PALLET_COUNT: Final[str] = "Analiza la imagen adjunta y devuelve el conteo de inventario según el formato JSON de salida estricto."

```

### **3.5 Cliente Gemini (placeholder “enchufable”)**

```py

# src/llm/gemini_client.py - Actualizado con uso de response_schema y Minified models
from typing import List, Tuple, Dict, Any
# Asume que el SDK real se importa así:
# from google import genai
# from google.genai.types import GenerationConfig
from pydantic import TypeAdapter

from src.models.schemas import (
    LLMFrameResult, FrameRef, LLMPalletObservation, LLMProductObservation, # Modelos internos de consolidación
    MinifiedFrameResult # Modelo compacto para la API
)
from src.llm.prompts import SYSTEM_PROMPT_PALLET_COUNT, USER_PROMPT_PALLET_COUNT
# Asumimos una función que convierte el path a un objeto compatible con la API de Gemini (e.g., FilePart)
# from src.preprocess.image_ops import path_to_gemini_part 

# --- SIMULACIÓN (Reemplazar con el SDK real de Gemini) ---
class MockResponse:
    def __init__(self, json_data):
        import json
        self._text = json.dumps(json_data)
    @property
    def text(self):
        return self._text

class MockGeminiSDK:
    def generate_content(self, model_name, contents, config):
        # SIMULACIÓN de respuesta que respeta el esquema minificado
        mock_json_response = {
            "pallets": [
                {
                    "id": f"P_{abs(hash(tuple(contents))) % 1000}",
                    "p": [
                        {"n": "Leche UAT Entera 12x1L", "q": 84, "c": 0.93, "b": "Cremigal"}
                    ]
                }
            ]
        }
        return MockResponse(mock_json_response)

MOCK_SDK = MockGeminiSDK()
# ------------------------------------------------------------


class GeminiClient:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"): # Flash recomendado para visión rápida
        if not api_key:
            raise RuntimeError("Falta GEMINI_API_KEY")
        self.api_key = api_key
        self.model_name = model_name
        # self.client = genai.Client(api_key=api_key) # Inicialización del cliente real

    def analyze_frames(self, frames: List[FrameRef], image_paths: List[str]) -> List[LLMFrameResult]:
        """
        Realiza una llamada (sin historial de chat) por cada frame para obtener un JSON Minificado.
        """
        results: List[LLMFrameResult] = []
        
        # 1. Generar el esquema JSON a partir del modelo Pydantic
        schema_json = MinifiedFrameResult.model_json_schema()
        
        # 2. Configuración de generación para forzar JSON usando el esquema
        config_dict = {
            "system_instruction": SYSTEM_PROMPT_PALLET_COUNT,
            "response_mime_type": "application/json",
            "response_schema": schema_json,
        }
        # En el SDK real, esto se haría con GenerationConfig

        for fr, path in zip(frames, image_paths):
            try:
                # Cargar imagen (asume path a archivo temporal de frame)
                # image_part = path_to_gemini_part(path) # Implementación real
                
                # Construir el 'contents' (System Prompt va en config)
                contents = [
                    # image_part, # Imagen cargada
                    USER_PROMPT_PALLET_COUNT,
                ]

                # 3. Llamada al SDK (Usando SIMULACIÓN)
                response = MOCK_SDK.generate_content(
                    model_name=self.model_name,
                    contents=contents,
                    config=config_dict
                )
                
                raw_text = response.text
                
                # 4. Parsear el JSON Minificado
                # La API es forzada, por lo que TypeAdapter no debería fallar
                minified_data = TypeAdapter(MinifiedFrameResult).validate_json(raw_text)
                
                # 5. Mapeo a los modelos internos de consolidación (LLMPalletObservation)
                llm_pallet_observations = []
                for m_pallet in minified_data.pallets:
                    llm_products = []
                    for m_product in m_pallet.p:
                        # Mapeo de claves cortas (Minified) a largas (LLMProductObservation)
                        prod_obs = LLMProductObservation(
                            brand=m_product.b,
                            product=m_product.n,
                            estimated_boxes=m_product.q,
                            confidence=m_product.c
                        )
                        llm_products.append(prod_obs)
                    
                    pallet_obs = LLMPalletObservation(
                        pallet_id=m_pallet.id,
                        products=llm_products
                    )
                    llm_pallet_observations.append(pallet_obs)
                
                results.append(
                    LLMFrameResult(
                        frame=fr,
                        pallets=llm_pallet_observations,
                        raw_text=raw_text,
                        model_name=self.model_name
                    )
                )

            except Exception as e:
                # RNF-06 (Robustez): Manejo de respuestas no parseables
                # El reintento con "repair JSON" (RF-07) se haría ANTES de este error
                print(f"Error procesando frame {fr.frame_idx}. Se asume una respuesta vacía: {e}")
                results.append(LLMFrameResult(frame=fr, pallets=[], raw_text=f"ERROR: {e}", model_name=self.model_name))
        
        return results


        return results
```

### **3.6 Consolidación (aplicando MAD \+ median)**

```py
# src/consolidate/consolidate.py
from collections import defaultdict
from typing import Dict, List, Tuple
import math
import statistics

from src.models.schemas import (
    LLMFrameResult, ConsolidatedResult, ConsolidatedPallet, ConsolidatedProduct, ConsolidationStats
)

def _mad(xs: List[int], med: float) -> float:
    return statistics.median([abs(x - med) for x in xs]) if xs else 0.0

def consolidate(video_id: str, frame_results: List[LLMFrameResult], n_target: int = 8) -> ConsolidatedResult:
    # pallet_id -> product_key -> list of (estimated, conf)
    buckets: Dict[str, Dict[str, List[Tuple[int, float]]]] = defaultdict(lambda: defaultdict(list))
    meta: Dict[str, Dict[str, str]] = defaultdict(dict)  # pallet_id->product_key->brand/product for output

    for fr in frame_results:
        for p in fr.pallets:
            for prod in p.products:
                key = (prod.brand or "") + "||" + prod.product
                buckets[p.pallet_id][key].append((prod.estimated_boxes, prod.confidence))
                meta[p.pallet_id][key] = {"brand": prod.brand or None, "product": prod.product}

    consolidated_pallets: List[ConsolidatedPallet] = []

    for pallet_id, prod_map in buckets.items():
        consolidated_products: List[ConsolidatedProduct] = []

        for key, obs in prod_map.items():
            xs = [x for x, _ in obs]
            cs = [c for _, c in obs]

            if not xs:
                continue

            med = float(statistics.median(xs))
            mad = float(_mad(xs, med))

            # Inliers por MAD
            if mad == 0:
                inliers = [(x, c) for (x, c) in obs if x == int(round(med))]
                if not inliers:
                    inliers = obs[:]  # fallback
            else:
                k = 3.0
                inliers = [(x, c) for (x, c) in obs if abs(x - med) <= k * mad]
                if not inliers:
                    inliers = obs[:]  # fallback

            xs_in = [x for x, _ in inliers]
            cs_in = [c for _, c in inliers]

            median_est = float(statistics.median(xs_in))
            est = int(round(median_est))

            conf_mean = sum(cs_in) / max(1, len(cs_in))
            stability_factor = math.exp(-(mad / max(1.0, med))) if med > 0 else (1.0 if mad == 0 else 0.5)
            coverage_factor = min(1.0, math.log(1 + len(inliers)) / math.log(1 + n_target))

            conf_final = max(0.0, min(1.0, conf_mean * stability_factor * coverage_factor))

            info = meta[pallet_id][key]
            consolidated_products.append(
                ConsolidatedProduct(
                    brand=info["brand"],
                    product=info["product"],
                    estimated_boxes=est,
                    confidence=conf_final,
                    evidence_frames=len(inliers),
                    stats=ConsolidationStats(
                        n_observations=len(obs),
                        min_est=min(xs),
                        max_est=max(xs),
                        median_est=median_est,
                        mad=mad
                    )
                )
            )

        consolidated_pallets.append(ConsolidatedPallet(pallet_id=pallet_id, products=consolidated_products))

    return ConsolidatedResult(video_id=video_id, pallets=consolidated_pallets)
```

### **3.7 Mapping a tu salida simple (FinalResult)**

```py
# src/io/outputs.py
from src.models.schemas import ConsolidatedResult, FinalResult, PalletEstimate, ProductEstimate

def to_final_result(consolidated: ConsolidatedResult) -> FinalResult:
    pallets = []
    for p in consolidated.pallets:
        products = [
            ProductEstimate(
                brand=cp.brand,
                product=cp.product,
                estimated_boxes=cp.estimated_boxes,
                confidence=cp.confidence
            )
            for cp in p.products
        ]
        pallets.append(PalletEstimate(pallet_id=p.pallet_id, products=products))

    return FinalResult(video_id=consolidated.video_id, pallets=pallets)
```

### **3.8 CLI (entrypoint)**

```py
# src/app.py
import json
from src.config import load_settings
from src.video.frames import extract_frames
from src.llm.gemini_client import GeminiClient
from src.consolidate.consolidate import consolidate
from src.io.outputs import to_final_result

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("video_path", type=str)
    parser.add_argument("--video-id", type=str, default="VID_001")
    parser.add_argument("--extract-fps", type=float, default=None)
    args = parser.parse_args()

    settings = load_settings()
    extract_fps = args.extract_fps if args.extract_fps is not None else settings.extract_fps

    frames = extract_frames(args.video_path, target_fps=extract_fps)

    # TODO: seleccionar N frames y generar image_paths (guardar frames seleccionados)
    selected_frames = frames[: settings.max_frames_to_send]
    image_paths = []  # TODO: rellenar con paths reales

    client = GeminiClient(api_key=settings.gemini_api_key)
    frame_results = client.analyze_frames(selected_frames, image_paths=image_paths)

    consolidated = consolidate(video_id=args.video_id, frame_results=frame_results)
    final = to_final_result(consolidated)

    print(json.dumps(final.model_dump(), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

---

