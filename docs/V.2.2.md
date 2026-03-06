## **Etapa 2.2.A — Endpoint “Create Inventory” con input flexible (Video o Photos)**

### **Objetivo**

Extender el **mismo endpoint** de creación de inventario para que pueda recibir **dos tipos de input**:

1. **Video** (comportamiento actual, sin cambios)  
2. **Conjunto de N fotos** (nuevo), con el fin de **reducir costo** y **latencia** al:  
* omitir extracción de frames desde video  
* enviar **menos imágenes** al LLM (Gemini hoy, providers futuros en etapas posteriores)

Esta etapa se limita a **contratos \+ validación \+ persistencia del input**.  
No introduce todavía Strategy Pattern ni refactors del pipeline (eso va en 2.2.B/2.2.D).

---

### **Alcance**

**Incluye**

* Actualizar el request schema del endpoint para soportar `input_type = "video" | "photos"`.  
* Validación estricta por tipo de input.  
* Persistencia de las fotos en el `run_dir` del job.  
* Registro de metadata del input (cantidad, orden, filenames, tamaños).  
* Mantener compatibilidad con clientes existentes (si hoy crean jobs con video).

**No incluye**

* Resizing/optimización de imágenes (Etapa 2.2.C).  
* Estrategias de obtención de frames (Etapa 2.2.B).  
* Strategy Pattern para LLM (Etapa 2.2.D).  
* Cambios a schema v2.1 o reglas de entidades.

---

### **Contrato del endpoint**

#### **Request (forma recomendada)**

Agregar campo explícito:

* `input_type`: `"video"` o `"photos"`

**Caso A — Video**

```json
{
  "input_type": "video",
  "video_path": "data/xxx.mp4",
  "mode": "hybrid"
}
```

**Caso B — Photos**

```json
{
  "input_type": "photos",
  "photos": [
    { "filename": "img_001.jpg", "content_base64": "..." },
    { "filename": "img_002.jpg", "content_base64": "..." }
  ],
  "mode": "hybrid"
}
```

#### **Compatibilidad hacia atrás (importante)**

Si hoy el endpoint recibe solo `video_path` sin `input_type`, definir una regla:

* Si `input_type` no viene y `video_path` existe → asumir `"video"`.

Esto evita romper integraciones.

---

### **Validaciones (reglas formales)**

#### **Reglas generales**

* `mode` se mantiene igual que hoy (ej: `"hybrid"`).  
* `input_type` ∈ {`video`, `photos`}.

#### **Video**

* `video_path` requerido y no vacío.  
* `photos` debe ser `null`/ausente.

#### **Photos**

* `photos` requerido.  
* `1 <= len(photos) <= MAX_PHOTOS_PER_JOB` (nuevo config).  
* Cada item:  
  * `filename` requerido (no vacío)  
  * `content_base64` requerido  
  * `content_base64` debe decodificar correctamente a bytes  
  * el contenido debe ser imagen (validación mínima):  
    * intentar decode con `cv2.imdecode` o `PIL.Image.open`  
* Validación de tamaño:  
  * `total_bytes <= PHOTOS_MAX_TOTAL_BYTES` (nuevo config)  
* Sanitización:  
  * `filename` debe convertirse a nombre seguro (no permitir `../`, `\`, etc.)  
  * guardar un nombre canonical: `0001_<slug(filename)>.jpg`

---

### **Persistencia del input (output de etapa A)**

#### **Estructura de directorios (mínima)**

Dentro de `run_dir`:

```
run/
  input_photos/
    0001_img_001.jpg
    0002_img_002.jpg
  input_manifest.json
```

*   
  `input_photos/` solo para `input_type="photos"`.  
* `input_manifest.json` siempre, con metadata del input.

#### **input\_manifest.json (contrato interno)**

Ejemplo:

```json
{
  "input_type": "photos",
  "photos": [
    {
      "index": 1,
      "original_filename": "img_001.jpg",
      "stored_filename": "0001_img_001.jpg",
      "bytes": 183245
    }
  ],
  "total_photos": 2,
  "total_bytes": 361234
}
```

Para video:

```json
{
  "input_type": "video",
  "video_path": "data/xxx.mp4"
}
```

**Nota:** esto es “audit trail” y además sirve para la Etapa 2.2.B (FrameSource).

---

### **Cambios esperados en el Job model**

Ampliar el registro del job (DB o filesystem, lo que uses) para guardar:

* `input_type`  
* `video_path` (si aplica)  
* `photos_dir` o `photos[]` (paths almacenados, no base64)  
* `input_manifest_path`

Esto evita que etapas posteriores dependan del request original.

---

### **Configuración (nueva)**

Agregar a `config.py`:

* `MAX_PHOTOS_PER_JOB` (default sugerido: 12\)  
* `PHOTOS_MAX_TOTAL_BYTES` (default sugerido: 25 \* 1024 \* 1024\)

*(Resizing/quality se deja para 2.2.C.)*

---

### **Manejo de errores (API)**

* Payload inválido → **422** con detalle claro (qué campo y por qué).  
* Fotos no decodifican → **422** (“invalid image content”).  
* Exceso de fotos o bytes → **413 Payload Too Large** o **422** (definir estándar y mantenerlo consistente).  
* `video_path` inexistente (si lo validás en create) → **404** o **422** según tu criterio actual.

---

### **Testing (mínimo requerido en etapa A)**

1. **Backward compatibility**  
* request sin `input_type` pero con `video_path` → se acepta como video.  
2. **Photos happy path**  
* 2 imágenes pequeñas base64 → crea job, persiste `input_photos/`, crea `input_manifest.json`.  
3. **Photos invalid base64**  
* rechaza 422\.  
4. **Photos invalid image bytes**  
* rechaza 422\.  
5. **Limits**  
* `len(photos) > MAX_PHOTOS_PER_JOB` → rechaza.  
* `total_bytes > PHOTOS_MAX_TOTAL_BYTES` → rechaza.  
6. **Filename sanitization**  
* filename con `../` → se guarda con nombre seguro y nunca escribe fuera de `run_dir`.

---

### **Criterios de aceptación (DoD) — Etapa 2.2.A**

* El endpoint acepta creación de inventario por **video** sin cambios de comportamiento.  
* El endpoint acepta creación de inventario por **photos** con validación y persistencia.  
* Se genera `run_dir/input_manifest.json` y, para photos, `run_dir/input_photos/*`.  
* Existen tests automatizados que cubren: compatibilidad video, happy path photos, invalid base64, invalid image, límites y sanitización.  
* No se cambió el core de v2.1 (entidades/reporting/evidence/review).

## **Etapa 2.2.B — FrameSource Strategy (Video vs Photos) y wiring al pipeline**

### **Objetivo**

Introducir una abstracción explícita para obtener “frames” (imágenes de entrada al análisis) sin modificar la lógica de negocio v2.1.

A partir de esta etapa, el pipeline deja de “saber” si el input vino de video o de fotos.  
Solo consume un `FramesBundle` (frames \+ metadata) provisto por una estrategia.

Esto habilita:

* mantener video **tal cual**  
* sumar fotos **sin duplicar pipeline**  
* garantizar determinismo  
* preparar el terreno para optimizaciones de costo (Etapa 2.2.C) y Strategy LLM (Etapa 2.2.D)

---

### **Alcance**

**Incluye**

* Crear `FrameSource` interface y dos implementaciones:  
  * `VideoFrameSource` (usa tu extractor actual)  
  * `PhotosFrameSource` (usa `input_manifest.json` \+ `input_photos/`)  
* Unificar la salida en un `FramesBundle` estándar.  
* Integrar en el pipeline (un solo punto de decisión por `input_type`).  
* Tests unitarios para ambas estrategias \+ smoke test del pipeline usando `FakeFrameSource` o `PhotosFrameSource`.

**No incluye**

* Resizing/compresión para reducir costo (Etapa 2.2.C).  
* Cambios en prompt/schema v2.1.  
* Cambios en Evidence Pack (solo asegurar compatibilidad).  
* Strategy Pattern de LLM providers (Etapa 2.2.D).

---

### **Diseño: contratos internos**

#### **1\) `FramesBundle` (contrato estándar)**

Crear dataclass:

**`src/frames/types.py`**

* `frames`: lista de frames (numpy arrays) **o** lista de paths (elegir uno y ser consistente)  
* `frame_refs`: ids/filenames/paths en el mismo orden  
* `metadata`: dict con info útil:  
  * `source`: `"video"` o `"photos"`  
  * `frame_w`, `frame_h` (si aplica)  
  * `count`: N  
  * `selected_by`: `"extract_representative_frames"` o `"uploaded_photos"`  
  * `input_manifest_path` (cuando sea photos)

**Recomendación práctica:** devolver **paths** a imágenes persistidas en `run_dir`, no arrays.  
Esto baja memoria, simplifica evidencia y hace el sistema más estable.

---

#### **2\) Interface `FrameSource`**

**`src/frames/sources/base.py`**

```py
class FrameSource(Protocol):
    def get_frames(self, *, job_id: str, run_dir: Path, job_input: dict) -> FramesBundle:
        ...
```

---

### **Implementaciones**

#### **A) `VideoFrameSource`**

**`src/frames/sources/video_source.py`**

Responsabilidad:

* Reutilizar 100% el comportamiento actual:  
  * extraer frames representativos  
  * persistirlos (si ya lo hacen) o mantener el output existente  
* Retornar `FramesBundle` con:  
  * `frames` \= paths a los frames seleccionados  
  * `frame_refs` \= filenames  
  * `metadata.source="video"`

**Importante:** esta clase debe ser un wrapper fino.  
No mover toda la lógica de video acá si ya existe: solo encapsular.

---

#### **B) `PhotosFrameSource`**

**`src/frames/sources/photos_source.py`**

Responsabilidad:

* Leer `run_dir/input_manifest.json`  
* Tomar la lista ordenada de fotos persistidas en `run_dir/input_photos/`  
* Retornar `FramesBundle` con:  
  * `frames` \= paths a esas fotos  
  * `frame_refs` \= filenames (o indexes)  
  * `metadata.source="photos"`  
  * `metadata.selected_by="uploaded_photos"`

Reglas:

* Orden debe ser determinista:  
  * por `index` del manifest (no por filesystem)  
* Si falta un archivo listado → error claro (job inválido/artefactos incompletos).

---

### **Selección de estrategia (Factory)**

**`src/frames/sources/factory.py`**

* `get_frame_source(input_type: str) -> FrameSource`

Map:

* `"video"` → `VideoFrameSource`  
* `"photos"` → `PhotosFrameSource`

---

### **Integración en el pipeline (wiring)**

Modificar **solo** el punto donde hoy se obtienen frames.  
Ejemplo conceptual:

Antes:

* pipeline llamaba directamente a `extract_representative_frames(video)`

Después:

* pipeline hace:  
  1. `frame_source = get_frame_source(job.input_type)`  
  2. `bundle = frame_source.get_frames(job_id, run_dir, job_input)`  
  3. `frames = bundle.frames` (paths)  
  4. LLM recibe esas imágenes  
  5. Evidence pack usa esas mismas refs

**Impacto esperado en v2.1:**

* `frames_selected` ahora se construye desde `FramesBundle.frame_refs` (video mantiene igual)  
* en modo photos, `frames_selected` será el set de imágenes subidas

---

### **Compatibilidad con Evidence Pack (2.1.D)**

Tu evidence pack hoy necesita:

* `frames` y `metadata` para:  
  * overview selection  
  * bbox cropping (si frame\_w/h está disponible, o leyendo la imagen)

Con `frames` como paths:

* evidence\_pack carga imagen cuando la necesita para sharpness/crop  
* `frame_w/h` se obtiene con lectura de la imagen (o cached)

**Recomendación:** en `FramesBundle.metadata` guardar `frame_dims` por frame si querés performance, pero no es requisito para 2.2.B.

---

### **Testing requerido (Etapa 2.2.B)**

#### **1\) Unit tests — `PhotosFrameSource`**

* given manifest con 3 fotos → devuelve `FramesBundle.frames` en el orden 1..3  
* si falta una foto → error  
* si manifest corrupto → error claro

#### **2\) Unit tests — `VideoFrameSource` (mínimo)**

* mockear extractor existente → retorna paths esperados  
* metadata.source="video"

#### **3\) Pipeline wiring smoke test**

* crear job “photos” con manifest  
* correr pipeline con `FakeLLM` (mock)  
* assert:  
  * se invocó LLM con N imágenes  
  * report se genera  
  * frames\_selected \= N

---

### **Criterios de aceptación (DoD) — Etapa 2.2.B**

* Existe `FrameSource` interface y dos implementaciones (video/photos).  
* Pipeline obtiene frames únicamente vía `FrameSourceFactory`, sin `if` dispersos.  
* Video path no cambia funcionalmente (misma selección y resultados que antes).  
* Photos path produce `frames_selected` determinista (orden del manifest).  
* Evidence pack y report funcionan con ambas fuentes (sin cambios en contratos).  
* Tests cubren: PhotoSource ordering \+ missing file, VideoSource wrapper, pipeline smoke.

---

### **Archivos esperados (impacto)**

**Nuevos**

* `src/frames/types.py`  
* `src/frames/sources/base.py`  
* `src/frames/sources/video_source.py`  
* `src/frames/sources/photos_source.py`  
* `src/frames/sources/factory.py`

**Modificados**

* `src/pipeline/hybrid_inventory_pipeline.py` (solo el punto de obtención de frames)  
* tests (nuevos archivos de test)

---

## **Etapa 2.2.C — Optimización de costo/latencia para input `photos` (resizing, compresión y límites)**

### **Objetivo**

Hacer que el modo `input_type="photos"` sea **más barato y más rápido** de forma controlada, sin afectar:

* el modo video (sin cambios),  
* el core v2.1 (entidades, report, evidence, review),  
* la auditabilidad del sistema.

Esta etapa introduce una “normalización” de imágenes de entrada para fotos, con **configuración explícita**, límites de tamaño, y métricas de impacto.

---

### **Alcance**

**Incluye**

* Límite de cantidad de fotos y tamaño total (si no quedó 100% cerrado en 2.2.A, acá se consolida).  
* Normalización de imágenes:  
  * decode → (opcional) resize → re-encode (JPG)  
* Persistencia consistente en `run_dir/input_photos/` como **artefactos estandarizados**.  
* Manifest extendido con métricas (original vs normalized).  
* Garantizar que el LLM reciba *las imágenes normalizadas* (no las originales).

**No incluye**

* Cambios en prompt/schema v2.1.  
* Cambios en evidence\_pack más allá de usar los frames ya normalizados.  
* Cambios en Strategy LLM (eso es 2.2.D).

---

## **Principios de diseño**

1. **Costo bajo control por config**  
   No hardcodear thresholds en el código; todo configurable.  
2. **Determinismo**  
   Con los mismos inputs y config, el output (paths \+ bytes) debe ser estable.  
3. **Auditabilidad sin explosión de storage**  
   * Guardar siempre normalized.  
   * Guardar original solo si hay un flag `PHOTOS_KEEP_ORIGINALS=true` (por defecto false).  
4. **Separación de responsabilidades**  
   * 2.2.A persistió el input.  
   * 2.2.C “normaliza” el set para consumo del pipeline/LLM.

---

## **Configuración requerida (nueva o consolidada)**

Agregar en `src/config.py`:

* `MAX_PHOTOS_PER_JOB: int = 12`  
* `PHOTOS_MAX_TOTAL_BYTES: int = 25 * 1024 * 1024` (25MB)  
* `PHOTO_RESIZE_MAX_SIDE: int = 1280`  
* `PHOTO_JPEG_QUALITY: int = 85`  
* `PHOTOS_KEEP_ORIGINALS: bool = false`  
* `PHOTOS_MIN_SIDE: int = 320` *(opcional, para rechazar miniaturas inútiles)*  
* `PHOTOS_DECODE_TIMEOUT_MS` *(opcional si te preocupa DoS por imágenes raras; MVP puede omitirse)*

**Nota:** si ya definiste límites en 2.2.A, mantenelos, pero 2.2.C los vuelve “operacionales”.

---

## **Arquitectura propuesta**

### **Dónde vive la normalización**

Implementarla como parte del **PhotosFrameSource** (Etapa 2.2.B) o como un módulo reutilizable:

Opción recomendada:

* `src/frames/normalize.py` con funciones puras  
* `PhotosFrameSource` la usa

Esto mantiene video aislado y evita meter lógica de imagen en rutas API.

---

## **Contrato de artefactos (run\_dir)**

```
run/
  input_photos/
    originals/                # solo si PHOTOS_KEEP_ORIGINALS=true
      0001_<slug>.jpg
    normalized/               # SIEMPRE
      0001_<slug>.jpg
      0002_<slug>.jpg
  input_manifest.json
```

*   
  `PhotosFrameSource` debe retornar **normalized paths**.  
* Evidence pack usará esas mismas.

---

## **Normalización: comportamiento exacto**

Para cada foto (en orden del manifest):

1. **Decode**  
* Validar que sea imagen real.  
2. **Validación mínima**  
* `min(width, height) >= PHOTOS_MIN_SIDE` (si aplica)  
* si no cumple: reject job con 422 (o marcar la foto como invalid y abortar; en v2.2 conviene abortar para evitar inputs basura).  
3. **Resize (si hace falta)**  
* si `max(width, height) > PHOTO_RESIZE_MAX_SIDE`:  
  * escalar manteniendo aspect ratio, con `max_side = PHOTO_RESIZE_MAX_SIDE`  
4. **Re-encode JPG**  
* Guardar como JPG con `PHOTO_JPEG_QUALITY`  
* Nombre determinista: `0001_<slug(filename)>.jpg`  
5. **Métricas**  
* bytes original  
* bytes normalized  
* dims original  
* dims normalized  
* resized: true/false

---

## **input\_manifest.json (extendido)**

Ejemplo:

```json
{
  "input_type": "photos",
  "total_photos": 3,
  "total_bytes_original": 32123456,
  "total_bytes_normalized": 7450123,
  "normalization": {
    "resize_max_side": 1280,
    "jpeg_quality": 85,
    "keep_originals": false
  },
  "photos": [
    {
      "index": 1,
      "original_filename": "IMG_001.PNG",
      "stored_original_path": null,
      "stored_normalized_path": "input_photos/normalized/0001_img_001.jpg",
      "original": { "bytes": 12300000, "w": 4032, "h": 3024 },
      "normalized": { "bytes": 2400000, "w": 1280, "h": 960 },
      "resized": true
    }
  ]
}
```

Esto te da:

* trazabilidad  
* analytics de costo  
* debugging real en producción

---

## **Integración con LLM (efecto real en costo)**

En v2.2, el LLM siempre recibe:

* para video: frames representativos (como hoy)  
* para photos: **solo** `normalized/` (N reducido, resoluciones acotadas)

Resultado esperado:

* menor tamaño de payload  
* menor latencia de upload  
* menor costo por imagen/tokenización (dependiendo del provider)

---

## **Testing requerido (Etapa 2.2.C)**

### **Unit tests — normalización**

1. **Resize aplica**  
* imagen 4000x3000 → normalized max\_side=1280 → dims correctas  
2. **Sin resize**  
* imagen 1024x768 → queda igual (pero re-encode a JPG igualmente)  
3. **Quality impact**  
* assert que bytes normalized \< bytes original (en un caso grande)  
4. **Determinismo**  
* misma imagen \+ config → mismo filename y path  
5. **Límites**  
* total\_bytes \> PHOTOS\_MAX\_TOTAL\_BYTES → rechaza  
* len(photos) \> MAX\_PHOTOS\_PER\_JOB → rechaza

### **Smoke test (photos)**

* job con 2 fotos grandes  
* verifica que `PhotosFrameSource` retorna paths en `normalized/`  
* evidence pack genera overview sin reventar

---

## **Criterios de aceptación (DoD) — Etapa 2.2.C**

* Para `input_type="photos"`, el sistema guarda y usa **imágenes normalizadas**.  
* Se aplican límites: cantidad y bytes totales.  
* `input_manifest.json` incluye métricas (original vs normalized).  
* El pipeline/LLM consumen `normalized/` siempre.  
* Video no cambia (regresión 0).  
* Tests cubren resize/no-resize, determinismo, límites.

---

## **Riesgos y mitigaciones**

### **Riesgo: perder detalle de etiquetas por resize**

Mitigación:

* `PHOTO_RESIZE_MAX_SIDE` configurable  
* si el warehouse tiene etiquetas pequeñas, subir a 1600/1920

### **Riesgo: overhead de CPU por re-encode**

Mitigación:

* normalizar solo en input photos (N acotado)  
* opcional: cache hash/sha256 para evitar procesar imágenes iguales (futuro)

### **Riesgo: storage si se guardan originales**

Mitigación:

* `PHOTOS_KEEP_ORIGINALS=false` por defecto

---

## **Prompt para Cursor (solo Etapa 2.2.C)**

```
/implement

Implement Stage 2.2.C: cost optimization for input_type="photos".

Requirements:
- Add configurable normalization for photos:
  - decode
  - resize if max(side) > PHOTO_RESIZE_MAX_SIDE
  - re-encode to JPG with PHOTO_JPEG_QUALITY
- Persist normalized images under run_dir/input_photos/normalized/
- Keep originals only if PHOTOS_KEEP_ORIGINALS=true
- Extend input_manifest.json with original/normalized metrics and normalization config snapshot
- Ensure PhotosFrameSource returns normalized paths (not originals)
- Enforce MAX_PHOTOS_PER_JOB and PHOTOS_MAX_TOTAL_BYTES
- Add unit tests for resize/no-resize, determinism, limits, and that pipeline consumes normalized paths.

Constraints:
- Do not change video logic.
- Do not change v2.1 entity/report logic.
- Keep changes minimal and testable.
```

---

## **Etapa 2.2.D — Strategy Pattern para LLM Providers (Gemini hoy, OpenAI/ChatGPT y futuros)**

### **Objetivo**

Desacoplar el pipeline del proveedor LLM específico (Gemini en v2.1) mediante un **Strategy Pattern** que permita:

* mantener **una sola llamada global** por job (igual que v2.1),  
* seleccionar proveedor/modelo por **config** y/o por request,  
* integrar otros LLMs (OpenAI/ChatGPT u otros) sin tocar el pipeline,  
* estandarizar métricas (latencia, tokens, errores) y manejo de retries/timeouts,  
* facilitar tests deterministas con un provider “fake”.

Esta etapa **no cambia**:

* schema v2.1,  
* parsing y reglas de entidades,  
* evidence pack,  
* assisted counting,  
* modo video/fotos (eso ya lo resolviste en A/B/C).

---

## **Alcance**

**Incluye**

* Definir interfaz `LLMProvider` (Strategy).  
* Implementar `GeminiProvider` como wrapper del cliente actual.  
* Implementar `OpenAIProvider` (lista para usar; si faltan keys, error claro).  
* Factory para seleccionar provider.  
* Request/Response “normalizados” (dataclasses) para observabilidad.  
* Refactor mínimo del pipeline para depender **solo** de la interfaz.

**No incluye**

* Fallback multi-provider (ej: “si Gemini falla, probar OpenAI”). Eso es otra etapa si lo querés.  
* Cambios de prompt/schema.  
* Auth/quotas/caching avanzado.

---

## **Principios de diseño**

1. **Pipeline no conoce providers**  
   El pipeline solo invoca `provider.analyze_global(frames, prompt, schema, metadata)`.  
2. **Contrato único de salida**  
   Todos los providers retornan un `dict` JSON que cumple el schema v2.1 (o fallan con error explícito).  
3. **Observabilidad homogénea**  
   Estandarizar:  
   * provider name, model  
   * latency\_ms  
   * token usage (si está disponible)  
   * error type (timeout, rate\_limit, invalid\_json)  
4. **Testabilidad**  
   Provider fake/fixture que retorna JSON controlado sin redes.

---

## **Diseño: módulos y contratos**

### **1\) Tipos comunes**

**`src/llm/types.py`**

* `LLMRequest`  
  * `job_id: str`  
  * `frames: list[Path] | list[np.ndarray]` *(ideal: paths, consistente con frames bundle)*  
  * `prompt: str`  
  * `schema_name: str` (ej `"global_analysis_v2_1"`)  
  * `schema: dict | None` (si tu provider lo soporta)  
  * `settings: LLMSettings`  
  * `metadata: dict` (input\_type, frame count, etc.)  
* `LLMSettings`  
  * `timeout_s: float`  
  * `max_retries: int`  
  * `temperature: float | None`  
  * `top_p: float | None`  
* `LLMResponse`  
  * `provider: str`  
  * `model: str`  
  * `latency_ms: int`  
  * `raw_text: str | None`  
  * `parsed_json: dict`  
  * `usage: dict | None` (tokens/cost si aplica)

Nota: si tu sistema hoy no usa “schema dict” de forma directa, dejalo opcional. Lo importante es normalizar output.

---

### **2\) Interfaz Strategy**

**`src/llm/providers/base.py`**

```py
from typing import Protocol
from src.llm.types import LLMRequest, LLMResponse

class LLMProvider(Protocol):
    name: str

    def analyze_global(self, request: LLMRequest) -> LLMResponse:
        ...
```

---

### **3\) Implementación Gemini (wrapper)**

**`src/llm/providers/gemini_provider.py`**

Responsabilidad:

* Adaptar tu llamada existente a Gemini para que:  
  * reciba `LLMRequest`  
  * construya el payload (prompt \+ imágenes)  
  * ejecute la llamada  
  * devuelva `LLMResponse(parsed_json=...)`

Detalles:

* No cambiar el prompt actual, solo moverlo a un lugar donde el pipeline lo consuma igual.  
* El parseo de JSON (si hoy lo hacés) debe quedar en el provider o en un helper común de parsing.

Errores:

* Timeout / invalid JSON / schema mismatch:  
  * lanzar excepción propia `LLMProviderError` con `code` y `message`.

---

### **4\) Implementación OpenAI (ChatGPT)**

**`src/llm/providers/openai_provider.py`**

Responsabilidad:

* Implementar llamada a OpenAI para:  
  * análisis multimodal (prompt \+ imágenes)  
  * retorno JSON  
* Si faltan credenciales:  
  * error claro: “OpenAI provider not configured”.

**Importante:** esta etapa puede dejar el provider “operativo” pero no necesariamente habilitado por default.

---

### **5\) Factory de providers**

**`src/llm/providers/factory.py`**

* `get_llm_provider(provider_name: str, config) -> LLMProvider`  
* Map:  
  * `"gemini"` → `GeminiProvider`  
  * `"openai"` → `OpenAIProvider`  
* default: `config.LLM_PROVIDER` (ej “gemini”)

---

### **6\) Errores comunes (normalizados)**

**`src/llm/errors.py`**

* `LLMProviderError(code: str, message: str, details: dict | None)`  
  * code ejemplos:  
    * `timeout`  
    * `rate_limit`  
    * `invalid_json`  
    * `provider_not_configured`  
    * `provider_failed`

Esto te permite:

* que API devuelva 502/503 con mensajes consistentes  
* logging controlado

---

## **Integración en el pipeline (mínimo diff)**

### **Antes (v2.1)**

El pipeline llama algo tipo “gemini\_global\_analysis(frames, prompt…)”.

### **Después (v2.2.D)**

1. Construye `LLMRequest` con:  
* job\_id  
* frames (paths)  
* prompt (el mismo)  
* schema info (v2.1)  
* settings desde config (timeout, retries)  
* metadata: input\_type, frames\_count  
2. Llama:  
* `provider = get_llm_provider(...)`  
* `resp = provider.analyze_global(request)`  
* `llm_json = resp.parsed_json`  
3. Continúa exactamente igual:  
* validate\_v21(llm\_json)  
* parse\_entities…

### **Donde se decide el provider**

* Por default: `config.LLM_PROVIDER`  
* Override opcional desde request (si lo querés):  
  * `llm_provider`, `llm_model`

Recomendación: permitir override pero con allowlist (“gemini|openai”), no string libre.

---

## **Compatibilidad con costos (fotos vs video)**

Con A/B/C ya resuelto:

* el provider recibe `frames` desde `FramesBundle`:  
  * video: frames representativos  
  * photos: normalized paths (N reducido)  
* y arma el payload con ese set.

Resultado: costo controlado sin tocar core.

---

## **Testing requerido (Etapa 2.2.D)**

### **1\) Fake Provider (sin redes)**

**`src/llm/providers/fake_provider.py`** (solo tests o dev)

* retorna un JSON fijo válido v2.1  
* permite simular invalid\_json, timeout, etc.

### **2\) Tests unitarios**

* `test_factory_selects_provider`  
* `test_provider_error_normalization`  
* `test_pipeline_uses_provider_interface`:  
  * inyectar fake provider  
  * assert que pipeline no llama Gemini directo  
  * assert que produce reporte igual

### **3\) Tests de contrato de salida**

* provider devuelve dict → pasa `validate_global_analysis_structure_v21()`

---

## **Criterios de aceptación (DoD) — Etapa 2.2.D**

* El pipeline depende solo de `LLMProvider` \+ `factory`.  
* Gemini funciona igual que en v2.1 (regresión 0).  
* Existe `OpenAIProvider` con implementación real (aunque no sea default).  
* Manejo de errores estandarizado (`LLMProviderError`).  
* Tests con fake provider y selección por factory.  
* No se agregó ninguna llamada extra al LLM (sigue siendo 1 por job).

---

## **Riesgos y mitigaciones**

### **Riesgo: diferencias de formato JSON entre providers**

Mitigación:

* obligación contractual: el provider debe retornar `parsed_json` en schema v2.1  
* validar con `validate_v21` igual que hoy

### **Riesgo: multimodal API de OpenAI cambia**

Mitigación:

* aislar completamente en `openai_provider.py`  
* tests con fake provider para CI  
* usar config para habilitarlo

### **Riesgo: “prompt drift” por provider**

Mitigación:

* el prompt se mantiene constante y se testea con fixtures  
* el provider solo “transporta” y parsea

---

## **Prompt para Cursor (solo Etapa 2.2.D)**

```
/implement

Implement Stage 2.2.D: LLM Provider Strategy Pattern.

Requirements:
- Introduce a Strategy interface LLMProvider with analyze_global(LLMRequest) -> LLMResponse.
- Implement GeminiProvider wrapping the existing Gemini code (no behavior change).
- Implement OpenAIProvider (real code), but not necessarily enabled by default.
- Add provider factory selection by config (and optional per-request override if already planned).
- Add normalized types (LLMRequest, LLMResponse, settings) and a common error type LLMProviderError.
- Refactor the pipeline to call ONLY the provider interface (no direct Gemini imports).
- Keep exactly ONE global LLM call per job.

Constraints:
- Do not change v2.1 schema, parsing, entity rules, evidence pack, or review API.
- Keep changes minimal and testable.
- Add tests using a FakeProvider to avoid network calls and ensure determinism.

Deliver:
- New modules under src/llm/
- Minimal pipeline refactor to use the provider factory
- Unit tests for provider factory, error normalization, and pipeline integration
```

---

## **Etapa 2.2.E — E2E/Integration Tests \+ Compatibilidad (video y photos) \+ verificación operativa**

### **Objetivo**

Cerrar el release v2.2 con una capa de pruebas que garantice:

* **Compatibilidad total** con v2.1 (modo video sin regresiones).  
* Funcionamiento completo del nuevo flujo **input\_type="photos"**.  
* Integración estable con:  
  * Evidence Pack (2.1.D)  
  * Assisted Counting API (2.1.E)  
  * Strategy LLM (2.2.D)  
  * FrameSource (2.2.B) y normalización (2.2.C)  
* Determinismo y contratos (report/evidence\_index/reviews) consistentes.

Esta etapa prioriza **tests de integración** (sin redes) con providers falsos/mocks, y un checklist operativo mínimo.

---

### **Alcance**

**Incluye**

* Tests E2E/integration (pipeline \+ API) para:  
  * creación por video  
  * creación por photos  
* Verificación de artefactos en `run_dir`:  
  * `hybrid_report.json`  
  * `evidence_index.json`  
  * `evidence/`  
  * `input_photos/normalized/` (photos)  
  * `reviews.json` (cuando se hace review)  
* Tests de endpoints críticos (Assisted Counting):  
  * listar entidades  
  * evidence endpoint  
  * POST review  
  * GET audit  
  * GET report resolved

**No incluye**

* Carga real a Gemini/OpenAI (no redes en CI).  
* Benchmarks de performance (pueden ser un follow-up).

---

## **Estrategia de testing**

### **Principio clave**

Los E2E deben correr **offline**:

* se reemplaza el LLM Provider por un `FakeProvider` que devuelve un JSON v2.1 fijo (fixture).  
* si querés probar “errores del provider”, el fake permite simular `invalid_json`, `timeout`, etc.

### **Tipos de tests**

1. **Integration Pipeline**: corre el pipeline “completo” en memoria/FS con un job real en un temp dir.  
2. **API Tests**: usa `TestClient` (si es FastAPI) contra el server con dependencias override (provider fake, output\_dir temp).

---

## **Fixtures recomendadas (golden files)**

Crear en `tests/fixtures/v2_1/`:

1. `global_analysis_ok.json`  
   * Un payload válido v2.1 con:  
     * 2 pallets countables  
     * 1 entity conflict por duplicate position\_barcode  
     * 1 NOT\_COUNTABLE / INVALID\_STRUCTURE (si querés cubrir branches)  
2. `global_analysis_unlocalized.json`  
   * Sin bboxes para obligar UNLOCALIZED en evidence.  
3. `photos/`  
   * 2–3 imágenes pequeñas sintéticas (o generadas en test con numpy y guardadas).  
4. `video_stub/` *(opcional)*  
   * Para no depender de un video real, el `VideoFrameSource` en tests se puede monkeypatchear para devolver frames ya existentes.

---

## **Matriz de pruebas (lo que sí o sí debe existir)**

### **1\) E2E — Video job (no regresión)**

**Test:** `test_e2e_video_job_generates_report_and_evidence`

**Arrange**

* Crear job input\_type=video (como se hacía en v2.1).  
* Mock `VideoFrameSource.get_frames` → devuelve 3 frames (paths).  
* FakeProvider devuelve `global_analysis_ok.json`.

**Assert**

* Se genera `hybrid_report.json` con:  
  * `mode` correcto  
  * `report_version` (si aplica)  
  * entities con `entity_uid`, `pallet_id`, `count_status`  
* Se genera `evidence_index.json`  
* Existe carpeta `evidence/`  
* Determinismo: ordenar entities estable (assert lista exacta de `entity_uid`/`pallet_id`).

---

### **2\) E2E — Photos job (nuevo flujo)**

**Test:** `test_e2e_photos_job_persists_normalized_and_generates_report`

**Arrange**

* Crear job input\_type=photos con 2–3 imágenes (base64 o paths).  
* Ejecutar normalización (2.2.C) o PhotosFrameSource que devuelve normalized.  
* FakeProvider devuelve `global_analysis_ok.json`.

**Assert**

* Existe `run_dir/input_photos/normalized/*`  
* `input_manifest.json` contiene:  
  * total\_bytes\_original/normalized  
  * paths normalized  
* `hybrid_report.json` generado  
* `evidence_index.json` generado  
* LLM recibió N imágenes (si el FakeProvider registra el request).

---

### **3\) Evidence — UNLOCALIZED vs LOCALIZED (integración)**

**Test:** `test_e2e_evidence_localization_modes`

**Arrange**

* Correr photos job con payload `global_analysis_unlocalized.json` y luego con `global_analysis_ok.json`.

**Assert**

* En un caso: `evidence_localization="UNLOCALIZED"` y no existen `position_label_*` / `product_label_*`.  
* En otro: `LOCALIZED` y existen crops (si bboxes presentes).

---

### **4\) Assisted Counting API — Flujo completo (photos)**

**Test:** `test_api_review_flow_photos_job`

**Arrange**

* Crear job photos que termina `SUCCEEDED` y tiene `evidence_index.json`.  
* Usar TestClient:  
  * GET `/entities?status=NEEDS_REVIEW` (o sin filtro)  
  * GET `/entities/{entity_uid}/evidence`  
  * POST `/entities/{entity_uid}/review` (SET\_COUNT)  
  * GET `/entities/{entity_uid}/audit`  
  * GET `/report?resolved=true`

**Assert**

* POST review crea `reviews.json`.  
* Audit devuelve el evento.  
* Resolved report muestra `count_status=COUNTED_MANUAL` y `final_quantity` override.  
* Summary recomputa y refleja `counted_manual`.

---

### **5\) Provider Strategy — Wiring (sin redes)**

**Test:** `test_pipeline_uses_llm_provider_strategy`

**Arrange**

* Config `LLM_PROVIDER=fake`  
* Factory devuelve FakeProvider

**Assert**

* No se importó ni se llamó código Gemini directo (assert indirecto: monkeypatch, o spy al wrapper).  
* request contiene metadata: input\_type, frame\_count, schema\_name.

---

## **Reglas de compatibilidad (lo que se verifica explícitamente)**

* Video path debe seguir generando:  
  * mismo tipo de reporte que v2.1  
  * mismas keys (o solo additive)  
* Photos path debe generar:  
  * reporte equivalente  
  * `frames_selected` acorde al N subido (si lo exponés)  
* Ningún endpoint existente cambia su firma de forma incompatible.

---

## **Criterios de aceptación (DoD) — Etapa 2.2.E**

* Existe al menos 1 E2E para **video** y 1 E2E para **photos**.  
* Evidence pack verificado en ambos flujos.  
* Assisted Counting API verificado en al menos un flujo (ideal photos).  
* Strategy LLM verificada con FakeProvider (sin redes).  
* CI verde (tests offline deterministas).  
* “Golden fixtures” versionados y documentados.

---

## **Checklist operativo mínimo (para vos / QA)**

Esto no es test automático, pero sirve como “smoke manual”:

1. Crear job con photos (3 imágenes)  
2. Ver que existan:  
   * `input_photos/normalized`  
   * `hybrid_report.json`  
   * `evidence_index.json`  
3. Listar entidades por API y abrir evidence  
4. Hacer un review y pedir report resolved

---

## **Prompt para Cursor (solo Etapa 2.2.E)**

```
/implement

Implement Stage 2.2.E: E2E/integration tests and compatibility verification for v2.2.

Requirements:
- Add offline integration tests for:
  1) video job path (no regression)
  2) photos job path (new)
  3) evidence LOCALIZED vs UNLOCALIZED behavior
  4) assisted counting API full flow (review + audit + resolved report)
  5) verify pipeline uses LLM Provider Strategy (FakeProvider), no network calls

Test constraints:
- No real Gemini/OpenAI calls.
- Use fixtures (global_analysis_ok.json, global_analysis_unlocalized.json) under tests/fixtures/.
- Use temp directories for run/output.
- Keep tests deterministic and fast.

Deliver:
- New/updated test files
- Fixtures
- Any minimal dependency overrides needed (TestClient overrides, factory injection)
- A short “how to run tests” note
```

---

## **Etapa 2.2.F — Hard Cleanup (remover modo legacy \+ borrar código no usado \+ estabilización final)**

### **Objetivo**

Cerrar el release v2.2 con una revisión extensa del código para:

* eliminar el **modo legacy** por completo (runtime \+ config \+ rutas \+ tests \+ docs),  
* borrar **código no utilizado** y duplicado,  
* simplificar ramas condicionales (menos “if legacy/hybrid”),  
* consolidar convenciones y puntos únicos de verdad,  
* mejorar mantenibilidad y reducir superficie de bugs.

Esta etapa debe hacerse con **cambio mínimo de comportamiento** para el flujo soportado (v2.2: video \+ photos \+ hybrid v2.1/v2.2).

---

## **Principios de ejecución (para no romper el sistema)**

1. **Eliminar en capas**  
* Primero: cortar accesos (feature flags, rutas).  
* Segundo: borrar implementaciones.  
* Tercero: limpiar tests, docs, imports, dead code.  
2. **Siempre con tests verdes**  
* Cada “sub-etapa” debe dejar CI verde.  
* Evitar un mega-commit sin red.  
3. **Nunca borrar sin rastrear referencias**  
* Cada borrado tiene que estar respaldado por:  
  * `grep` de referencias  
  * test coverage que asegura que el flujo moderno sigue OK

---

## **Alcance**

**Incluye**

* Remover “legacy mode” de:  
  * config  
  * pipeline  
  * API request parsing  
  * report generation (si hay legacy report)  
  * docs y ejemplos CLI  
  * tests legacy  
* Eliminar módulos obsoletos y helpers duplicados.  
* Consolidar:  
  * validación de inputs  
  * path helpers  
  * contratos de reporte y evidence  
  * entrypoints del pipeline  
* Revisión de seguridad básica:  
  * validación job\_id/entity\_uid  
  * no path traversal  
  * slug/paths consistentes

**No incluye**

* Cambios funcionales grandes (nuevo algoritmo de conteo, nuevo schema).  
* Reescritura de arquitectura (solo limpieza/refactor controlado).

---

## **Inventario de cosas a remover (checklist)**

### **1\) Modo legacy (hard delete)**

Eliminar completamente:

* flags:  
  * `mode="legacy"` o variantes  
  * config relacionadas (thresholds legacy)  
* ramas condicionales:  
  * `if mode == "legacy": ... else: ...`  
* archivos/módulos:  
  * `legacy_pipeline.py`, `legacy_report.py`, `legacy_*`  
  * “visual fallback” si era exclusivo legacy  
* endpoints legacy:  
  * rutas específicas legacy (si existen)  
* tests:  
  * `test_legacy_*`

**Criterio “legacy eliminado”:**

* `ripgrep -n "legacy"` devuelve:  
  * 0 matches de lógica productiva (permitido solo en changelog o comentario histórico)  
* No existe en OpenAPI / docs / README.

---

### **2\) Código no usado / duplicado**

Objetivo: reducir duplicación típica de:

* hashing/dedupe de imágenes (si aparece en más de un módulo)  
* path helpers repetidos  
* normalización de inputs en más de un lugar  
* parsing/validation duplicado

**Regla:** un solo módulo por responsabilidad:

* `src/frames/*` para input frames  
* `src/llm/*` para providers  
* `src/evidence/*` para evidence pack  
* `src/review/*` para review/resolved

---

### **3\) Simplificación del pipeline**

Una vez removido legacy, la pipeline debería tener:

* 1 camino principal “hybrid” (v2.1/v2.2)  
* input flexible (video/photos) resuelto por FrameSourceStrategy  
* LLM resuelto por ProviderStrategy  
* evidence/review opcionales pero sin bifurcaciones profundas

**Resultado esperado:**

* pipeline con menor complejidad ciclomática  
* menos `try/except` amplios  
* mejor logging y errores

---

## **Plan de trabajo recomendado (sub-etapas internas)**

### **2.2.F1 — “Disable legacy” (corte de entrada)**

* Remover `legacy` de enums/validaciones del request.  
* Si hoy permitís `mode="legacy"`, devolver 422 con mensaje:  
  * `"legacy mode has been removed as of v2.2"`

✅ Tests deben actualizarse para no intentar legacy.

---

### **2.2.F2 — Borrado de implementación legacy**

* Borrar módulos legacy.  
* Borrar funciones legacy no referenciadas.  
* Ajustar imports en pipeline/routers.

✅ `pytest` verde.

---

### **2.2.F3 — Cleanup de rutas, docs y ejemplos**

* README / docs de ejecución  
* ejemplos de payload  
* referencias a legacy en documentación interna

✅ build/documentación coherente.

---

### **2.2.F4 — Dead code y duplicación**

* Unificar:  
  * hashing/dedupe  
  * path utils  
  * validación de ids (job\_id, entity\_uid)  
* Eliminar helpers no usados.  
* Reducir “acoplamientos raros” (routes importando routes, etc.)

✅ `ruff/flake8` si aplica (opcional), tests verdes.

---

### **2.2.F5 — “Branch review” final del release (calidad)**

* Revisar:  
  * naming  
  * consistencia de report schema  
  * manejo de errores API  
  * determinismo  
  * límites y storage

✅ Check final con lista de verificación.

---

## **Tests mínimos que deben pasar al final de 2.2.F**

* Todos los E2E de 2.2.E  
* Tests unitarios de:  
  * FrameSource video/photos  
  * normalización photos  
  * LLM factory \+ fake provider  
  * evidence pack  
  * review merge/resolved

**Y adicional:** tests que aseguren que legacy no existe:

* `test_create_job_rejects_legacy_mode`  
* `test_no_legacy_imports` *(opcional: sanity check con import graph liviano)*

---

## **Criterios de aceptación (DoD) — Etapa 2.2.F**

* El modo legacy no se puede usar (API lo rechaza) y no existe código runtime legacy.  
* Se eliminaron módulos legacy y tests asociados.  
* No hay referencias productivas a “legacy” en el repo.  
* Pipeline principal quedó simplificado (menos ramas y duplicación).  
* Tests E2E/CI verdes.  
* Docs/README actualizados al flujo v2.2.

---

## **Prompt para Cursor (solo Etapa 2.2.F)**

```
/implement

Implement Stage 2.2.F: Hard cleanup and legacy removal.

Goals:
1) Remove legacy mode completely:
   - requests must reject mode="legacy" (422 with clear message)
   - delete legacy pipeline/report/modules
   - remove legacy routes and legacy tests
   - remove legacy config flags
2) Delete unused code and reduce duplication:
   - unify hashing/dedupe utilities (single source)
   - unify path helpers (single source)
   - unify validation helpers (job_id/entity_uid)
3) Simplify the pipeline:
   - keep one main hybrid flow
   - keep FrameSourceStrategy (video/photos) and LLMProviderStrategy
   - remove deep branching and dead fallback paths

Rules:
- Keep current supported behavior intact (video + photos).
- Do not introduce functional changes beyond removing legacy and dead code.
- Ensure all tests remain green; update tests accordingly.
- After cleanup, `rg -n "legacy"` should return no runtime references (docs/changelog ok).

Deliver:
- A list of deleted files
- Updated modules with minimal diffs
- Updated tests
- A short verification checklist (commands + expected outputs)
```

---

## **Comandos concretos (para vos, fuera de Cursor) para auditar el cleanup**

*(Esto ayuda muchísimo cuando haces la etapa F)*

1. Encontrar legacy:

```shell
rg -n "legacy" src tests docs
```

2.   
   Ver imports muertos (rápido):

```shell
python -m compileall src
```

3.   
   Correr tests:

```shell
pytest -q
```

---

