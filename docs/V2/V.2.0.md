Perfecto.  
Eso cambia bastante el enfoque técnico de la Etapa 1\.

Si hoy no estás usando YOLO y el sistema está basado en Gemini Vision, entonces la reestructuración del core debe respetar eso: el motor actual es LLM-first, no CV-first.

Te paso la **ETAPA 1 en limpio**, en formato profesional, lista para documento interno.

---

# **📘 Dinamic Systems**

# **Inventory Engine v2.0**

## **ETAPA 1 — Reestructuración Arquitectónica del Core**

### **(Convivencia de Versiones \+ Selector por CLI)**

---

## **1️⃣ Contexto**

La versión actual del sistema (v1.x):

* Procesa video mediante Gemini Vision API.  
* Analiza frames o recortes.  
* Realiza conteo visual inteligente.  
* Genera reportes estructurados.  
* Está optimizada para escenarios sin etiquetas confiables.

La versión 2.0 introduce un cambio estratégico:

El sistema pasará a priorizar lectura de etiquetas (metadata-first),  
utilizando conteo visual como mecanismo de respaldo.

Para lograr esto sin romper estabilidad operativa, se requiere una reestructuración del núcleo del sistema.

---

## **2️⃣ Objetivo de la Etapa 1**

Crear una nueva capa de orquestación que permita:

* Ejecutar la versión actual del sistema sin modificaciones.  
* Preparar el sistema para integrar el modo híbrido.  
* Separar claramente responsabilidades.  
* Permitir selección de modo vía CLI.  
* Mantener compatibilidad total con v1.x.

Esta etapa **no implementa lógica de etiquetas**.

Es una etapa exclusivamente estructural.

---

## **3️⃣ Principio de Diseño**

Separación explícita entre:

* Motor Visual Actual (v1.x)  
* Nuevo Motor Híbrido (v2.0)  
* Capa de Decisión Superior

El sistema deja de tener un flujo único y pasa a tener un controlador central.

---

## **4️⃣ Nuevo Modelo Arquitectónico**

```
Video
   ↓
HybridInventoryPipeline (controlador)
   ↓
   ├── LegacyVisualPipeline  (v1.x)
   └── HybridMode (v2.0 — futuro)
```

La versión actual no se elimina.  
Se encapsula.

---

## **5️⃣ Selector de Modo vía CLI**

Se incorpora un parámetro obligatorio de ejecución:

```shell
python run.py video.mp4 --mode legacy
python run.py video.mp4 --mode hybrid
```

### **Comportamiento:**

* `--mode legacy` → ejecuta exactamente la versión actual.  
* `--mode hybrid` → ejecuta la estructura nueva (por ahora delega al legacy).

### **Valor por defecto:**

```shell
--mode legacy
```

Esto evita romper producción o pruebas existentes.

---

## **6️⃣ Nueva Clase Principal**

Se introduce:

```py
class HybridInventoryPipeline:
```

### **Responsabilidades:**

* Recibir parámetros CLI.  
* Decidir qué motor ejecutar.  
* Delegar procesamiento.  
* Unificar interfaz pública del sistema.

No ejecuta lógica interna de análisis.

Es un controlador de alto nivel.

---

## **7️⃣ Encapsulación de la Versión Actual**

Se crea una clase:

```py
class LegacyVisualPipeline:
```

Esta clase:

* Contiene todo el flujo actual basado en Gemini.  
* No se modifica internamente.  
* Se convierte en módulo autónomo ejecutable.

Ejemplo conceptual:

```py
class HybridInventoryPipeline:

    def __init__(self):
        self.legacy_pipeline = LegacyVisualPipeline()

    def process_video(self, path: str, mode: str = "legacy"):

        if mode == "legacy":
            return self.legacy_pipeline.run(path)

        elif mode == "hybrid":
            return self.run_hybrid(path)

        else:
            raise ValueError("Invalid mode")
```

En esta etapa, `run_hybrid()` simplemente redirige al legacy.

---

## **8️⃣ Cambios en run.py**

El entry point del sistema debe:

* Parsear argumento `--mode`.  
* Instanciar `HybridInventoryPipeline`.  
* Ejecutar `process_video()`.

Ejemplo conceptual:

```py
pipeline = HybridInventoryPipeline()

pipeline.process_video(
    path=video_path,
    mode=args.mode
)
```

---

## **9️⃣ Resultado Esperado al Final de la Etapa 1**

Al completar esta etapa:

* El sistema admite múltiples modos.  
* La versión actual funciona exactamente igual.  
* Existe una nueva capa de control desacoplada.  
* No se ha modificado lógica de análisis con Gemini.  
* El sistema queda preparado para bifurcación por pallet en Etapa 2\.

---

## **🔟 Criterios de Validación**

Checklist de cierre:

* CLI acepta `--mode`.  
* Modo legacy produce resultados idénticos a v1.x.  
* Modo hybrid ejecuta sin errores.  
* No se alteró comportamiento interno.  
* No se afectó estructura de reporte actual.

---

## **1️⃣1️⃣ Impacto Estratégico**

Esta etapa transforma el sistema de:

Script lineal

a:

Plataforma modular con control de estrategia.

Es la base necesaria para:

* Introducir lógica de etiquetas.  
* Implementar decisión dinámica pallet por pallet.  
* Mantener convivencia entre versiones.

---

## **ETAPA 2 — Análisis Global por Video (Single Gemini Call Strategy)**

---

# **1️⃣ Contexto**

En la versión 2.0 del sistema se introduce un cambio estratégico:

Reducir la cantidad de llamadas a Gemini a una única llamada por video.

Dado que:

* El dron recorre el pasillo una sola vez.  
* Cada pallet aparece una única vez en el recorrido.  
* No hay revisitas ni loops.

Es técnicamente viable realizar un análisis global consolidado.

---

# **2️⃣ Objetivo de la Etapa 2**

Implementar un modelo de análisis en el cual:

* Se extraen frames representativos del video.  
* Se realiza una única llamada a Gemini Vision.  
* Gemini detecta todos los pallets visibles.  
* Gemini identifica cuáles tienen etiqueta.  
* Gemini extrae código interno y cantidad cuando exista.  
* Gemini identifica pallets sin etiqueta.

El sistema pasa a ser:

Video → Análisis Global → Lista estructurada de pallets

---

# **3️⃣ Nuevo Modelo Conceptual**

Antes (v1.x):

```
Video → Análisis por frames → Conteo
```

Ahora (v2.0):

```
Video
   ↓
Extracción de frames estratégicos
   ↓
1 llamada Gemini
   ↓
Respuesta estructurada
   ↓
Lista de pallets
```

---

# **4️⃣ Extracción de Frames Representativos**

Para evitar enviar todos los frames y saturar tokens, el sistema debe:

* Extraer entre 15 y 30 frames estratégicos.  
* Distribuirlos uniformemente a lo largo del video.  
* Incluir frames donde hay transición entre pallets.

Ejemplo para video de 2 minutos:

* 1 frame cada 4–6 segundos.  
* Total estimado: 20 frames.

Objetivo:

Capturar cada pallet al menos una vez.

---

# **5️⃣ Responsabilidad de Gemini**

En la única llamada, Gemini debe:

1. Detectar cuántos pallets distintos aparecen en el video.  
2. Separarlos como entidades independientes.  
3. Determinar si cada pallet tiene etiqueta visible.  
4. Si tiene etiqueta:  
   * Extraer `internal_code`.  
   * Extraer `quantity`.  
5. Si no tiene etiqueta:  
   * Estimar cantidad visible.  
   * Marcarlo como fallback.

---

# **6️⃣ Estructura Esperada de Respuesta**

Respuesta obligatoriamente estructurada en JSON:

```json
{
  "total_pallets_detected": 4,
  "pallets": [
    {
      "pallet_id": "P1",
      "has_label": true,
      "internal_code": "10145317",
      "quantity": 15,
      "confidence": 0.94
    },
    {
      "pallet_id": "P2",
      "has_label": false,
      "estimated_visible_boxes": 12,
      "confidence": 0.78
    }
  ]
}
```

Reglas:

* No duplicar pallets.  
* No inventar pallets.  
* No fusionar pallets distintos.  
* Si hay duda, reducir confianza.

---

# **7️⃣ Rol del Sistema Después de la Respuesta**

Una vez recibida la respuesta:

El sistema debe:

* Parsear JSON.  
* Validar estructura.  
* Verificar que `quantity` sea numérico cuando `has_label = true`.  
* Asignar:

```
processing_mode = "label" | "visual_fallback"
```

*   
  Generar reporte pallet-level.

---

# **8️⃣ Nueva Entidad Pallet (v2.0)**

```py
class Pallet:

    def __init__(self, pallet_id):
        self.id = pallet_id
        self.has_label = False
        self.internal_code = None
        self.quantity = None
        self.estimated_visible_boxes = None
        self.processing_mode = None
        self.confidence = None
```

---

# **9️⃣ Ventajas del Enfoque**

* 🔥 Solo 1 llamada a Gemini por video.  
* 🔥 Costos completamente controlados.  
* 🔥 Arquitectura simple.  
* 🔥 Sin tracking.  
* 🔥 Sin detección por cambio.  
* 🔥 Sin complejidad temporal.

---

# **🔟 Limitaciones Aceptadas**

Este modelo asume:

* El dron pasa una sola vez.  
* No hay revisitas.  
* No hay loops.  
* No se requiere trazabilidad frame-by-frame.

No es un modelo determinista temporal.  
Es un modelo de inferencia global.

---

# **1️⃣1️⃣ Métricas de Éxito**

Al finalizar la Etapa 2:

* El sistema realiza 1 sola llamada a Gemini.  
* Detecta correctamente pallets distintos.  
* Identifica cuáles tienen etiqueta.  
* Genera estructura pallet-level.  
* Reduce drásticamente uso de API.

---

# **1️⃣2️⃣ Impacto Arquitectónico**

Después de esta etapa:

* El sistema deja de ser frame-driven.  
* Se vuelve video-level structured.  
* El pallet es entidad primaria.  
* Se prepara la Etapa 3 (Label Parsing y Validación Estricta).

---

# **📌 Conclusión**

La Etapa 2 redefine el núcleo del sistema bajo un modelo:

Single Global Inference per Video

Es una fase estratégica de optimización y simplificación.

---

Perfecto.  
Entonces vamos con **mínimo indispensable**.

Eso es lo correcto para esta arquitectura:

* Menos tokens  
* Menos ambigüedad  
* Menos superficie de error  
* Más robustez de parsing

Ahora te entrego la **ETAPA 3 definitiva**, ajustada a ese criterio.

---

## 

## **ETAPA 3 — Diseño del Prompt Global Minimalista y Determinista**

---

# **1️⃣ Objetivo**

Diseñar un prompt que permita:

* Analizar un conjunto de frames representativos del video.  
* Detectar todos los pallets distintos.  
* Determinar si cada pallet tiene etiqueta.  
* Extraer únicamente lo indispensable para operación.  
* Devolver JSON estrictamente válido.  
* Minimizar riesgo de alucinación.

Sin información adicional innecesaria.

---

# **2️⃣ Principio de Diseño**

En este modelo:

Menos información solicitada \= menos margen de error.

No pedimos:

* Descripciones visuales.  
* Posiciones (left/right).  
* Detalles adicionales.  
* Metadata estética.

Solo pedimos lo que impacta directamente en negocio:

* Existencia de etiqueta.  
* Código interno.  
* Cantidad.  
* Estimación si no hay etiqueta.  
* Confianza.

Nada más.

---

# **3️⃣ Estructura Definitiva de Respuesta**

Gemini debe devolver exactamente:

```json
{
  "total_pallets_detected": integer,
  "pallets": [
    {
      "pallet_id": "P1",
      "has_label": true or false,
      "internal_code": string or null,
      "quantity": integer or null,
      "estimated_visible_boxes": integer or null,
      "confidence": float between 0 and 1
    }
  ]
}
```

Reglas obligatorias:

* `total_pallets_detected` debe coincidir con longitud del array.  
* Si `has_label = true` → `quantity` debe ser número.  
* Si `has_label = false` → `estimated_visible_boxes` debe ser número.  
* Si no puede determinarse un valor → null.  
* No texto adicional.

---

# **4️⃣ Prompt Oficial v2.0 — Single Call Minimal**

Este es el prompt listo para producción:

---

You are analyzing multiple representative frames extracted from a warehouse aisle video.

The drone passes each pallet only once.

Your task is to detect all distinct pallets visible across the frames.

Important constraints:

* Each pallet must appear only once.  
* Do NOT duplicate pallets.  
* Do NOT merge different pallets.  
* Do NOT invent pallets.  
* If uncertain, reduce confidence.  
* If a value cannot be clearly read, return null.

For each pallet:

* Determine if a logistics label is visible.  
* If a label is visible:  
  * Extract the internal\_code.  
  * Extract the quantity.  
* If no label is visible:  
  * Estimate the number of visible boxes.

Return STRICT JSON using this exact structure:

{  
"total\_pallets\_detected": integer,  
"pallets": \[  
{  
"pallet\_id": "P1",  
"has\_label": true or false,  
"internal\_code": string or null,  
"quantity": integer or null,  
"estimated\_visible\_boxes": integer or null,  
"confidence": float between 0 and 1  
}  
\]  
}

Important:

* Return ONLY valid JSON.  
* No explanations.  
* No markdown.  
* No comments.  
* No extra text.  
* No trailing commas.

---

# **5️⃣ Validación Post-Procesamiento (Crítica)**

El sistema debe implementar validaciones automáticas:

1. JSON parseable.  
2. `total_pallets_detected == len(pallets)`.  
3. No pallet\_id duplicados.  
4. Reglas de consistencia:  
   * has\_label true → quantity \!= null.  
   * has\_label false → estimated\_visible\_boxes \!= null.  
5. Confidence entre 0 y 1\.

Si falla alguna:

→ Intentar 1 reintento de corrección.  
→ Si falla nuevamente, marcar como error de análisis.

---

# **6️⃣ Ventajas del Diseño Minimalista**

* Reduce tokens.  
* Reduce riesgo de narrativa.  
* Reduce errores de formato.  
* Reduce ambigüedad.  
* Mejora estabilidad del sistema.

---

# **7️⃣ Resultado al Final de la Etapa 3**

* Realiza una sola llamada por video.  
* Obtiene pallets estructurados.  
* Sabe cuáles usarán label mode.  
* Sabe cuáles requerirán fallback.  
* Está listo para Etapa 4 (Integración Operativa).

Perfecto.  
Ahora entramos en una etapa estructural clave: convertir la inteligencia del modelo en lógica operativa del sistema.

Hasta ahora:

* Etapa 1 → Reestructuración del core.  
* Etapa 2 → Análisis global con 1 llamada.  
* Etapa 3 → Prompt minimalista estructurado.

Ahora viene:

Transformar la respuesta de Gemini en comportamiento real del sistema.

---

## **ETAPA 4 — Integración Operativa del Análisis Global**

---

# **1️⃣ Objetivo**

Convertir la respuesta JSON de Gemini en:

* Entidades internas `Pallet`.  
* Decisión automática de procesamiento.  
* Generación de reporte estructurado.  
* Activación controlada de fallback si corresponde.

Esta etapa transforma:

Respuesta LLM → Sistema ejecutable.

---

# **2️⃣ Nuevo Flujo Operativo**

```
Video
   ↓
Extracción de frames
   ↓
1 llamada Gemini
   ↓
Parseo JSON
   ↓
Validación estructural
   ↓
Instanciación de Pallets
   ↓
Decisión por pallet:
        ├── Label Mode
        └── Visual Fallback
   ↓
Generación de reporte final
```

---

# **3️⃣ Parseo y Validación**

Una vez recibida la respuesta:

### **Paso 1 — Parseo seguro**

* Intentar `json.loads`.  
* Si falla → intento de corrección.  
* Si vuelve a fallar → error controlado.

---

### **Paso 2 — Validaciones estructurales obligatorias**

Checklist:

* `total_pallets_detected == len(pallets)`  
* No `pallet_id` duplicados.  
* Campos obligatorios presentes.  
* Reglas de coherencia:  
  * has\_label true → quantity \!= null.  
  * has\_label false → estimated\_visible\_boxes \!= null.  
* Confidence ∈ \[0,1\].

Si alguna regla falla:

→ Marcar video como “analysis\_invalid”.

---

# **4️⃣ Instanciación de Entidades Internas**

Por cada elemento del array:

```py
class Pallet:

    def __init__(self, pallet_id, has_label,
                 internal_code, quantity,
                 estimated_visible_boxes,
                 confidence):

        self.id = pallet_id
        self.has_label = has_label
        self.internal_code = internal_code
        self.quantity = quantity
        self.estimated_visible_boxes = estimated_visible_boxes
        self.confidence = confidence
        self.processing_mode = None
        self.final_quantity = None
```

---

# **5️⃣ Decisión Automática de Modo**

Reglas de negocio definidas previamente:

## **🔹 Caso 1 — Tiene etiqueta válida**

Condición:

* has\_label \= true  
* internal\_code \!= null  
* quantity \!= null

Acción:

```
processing_mode = "label"
final_quantity = quantity
```

No validación visual.  
Confianza total en etiqueta.

---

## **🔹 Caso 2 — No tiene etiqueta**

Condición:

* has\_label \= false

Acción:

```
processing_mode = "visual_fallback"
final_quantity = estimated_visible_boxes
```

(En esta versión experimental no se ejecuta conteo adicional,  
se usa lo que devolvió Gemini.)

---

# **6️⃣ Manejo de Edge Cases**

### **Caso A — 0 pallets detectados**

Opciones:

* Marcar video como vacío.  
* Registrar incidente.  
* No ejecutar fallback.

Decisión recomendada:

```
status = "no_pallets_detected"
```

---

### **Caso B — Confidence muy baja (\< 0.4)**

Podemos:

* Aceptar resultado.  
* O marcar como "low\_confidence\_review".

Recomendación:

No bloquear sistema en esta versión.  
Solo registrar flag.

---

# **7️⃣ Generación del Reporte Final**

Estructura final por pallet:

```json
{
  "pallet_id": "P1",
  "internal_code": "10145317",
  "quantity": 15,
  "source": "label",
  "confidence": 0.92
}
```

O:

```json
{
  "pallet_id": "P2",
  "internal_code": null,
  "quantity": 12,
  "source": "visual_fallback",
  "confidence": 0.78
}
```

---

# **8️⃣ Integración en HybridInventoryPipeline**

Método principal ahora queda:

```py
def run_hybrid(self, video_path):

    frames = extract_representative_frames(video_path)

    response = gemini_global_analysis(frames)

    validated_data = self.validate_response(response)

    pallets = self.build_pallet_objects(validated_data)

    self.assign_processing_modes(pallets)

    report = self.generate_report(pallets)

    return report
```

---

# **9️⃣ Resultado Esperado al Final de la Etapa 4**

* El sistema ejecuta completamente el flujo 1-call.  
* Genera lista estructurada de pallets.  
* Decide automáticamente label vs fallback.  
* Produce reporte consistente.  
* Maneja errores de parsing.  
* Registra estados especiales.

---

# **🔟 Estado del Sistema Tras Etapa 4**

Ahora el sistema:

* Ya no depende del pipeline legacy para esta versión.  
* Ya opera en modo híbrido simplificado.  
* Está listo para evaluación real en campo.

---

## **ETAPA 5 — Optimización Inteligente de Selección de Frames**

---

# **1️⃣ Objetivo**

Diseñar un sistema que seleccione automáticamente los frames más representativos del video para:

* Maximizar visibilidad de cada pallet.  
* Reducir redundancia.  
* Minimizar cantidad de frames enviados.  
* Mantener 1 sola llamada a Gemini.  
* Controlar tokens.

---

# **2️⃣ Problema Actual**

Si extraemos frames uniformemente (ej: cada 5 segundos):

* Puede que justo un pallet esté en transición.  
* Puede que la etiqueta esté parcialmente visible.  
* Puede que haya frames redundantes del mismo pallet.

Eso reduce calidad del análisis global.

---

# **3️⃣ Principio de Optimización**

La selección de frames debe:

* Detectar cambios reales en la escena.  
* Priorizar estabilidad visual.  
* Evitar frames borrosos.  
* Evitar transiciones rápidas.  
* Garantizar cobertura completa del recorrido.

---

# **4️⃣ Nueva Estrategia de Selección (Propuesta)**

Se implementa un sistema de 3 filtros combinados:

---

## **🔹 Filtro 1 — Muestreo Base**

Extraer frames uniformemente:

Ejemplo:

```
video_duration = 120s
base_interval = 4s
→ ~30 frames
```

Esto garantiza cobertura general.

---

## **🔹 Filtro 2 — Eliminación de Redundancia**

Para cada frame extraído:

* Calcular firma visual simple (histograma o pHash liviano).  
* Comparar con último frame aceptado.  
* Si similitud \> umbral alto → descartar.

Esto elimina frames repetidos del mismo pallet estable.

---

## **🔹 Filtro 3 — Detección de Estabilidad**

Evitar frames en transición:

Criterio:

* Alta diferencia respecto al frame anterior  
* Movimiento abrupto  
* Motion blur elevado

Si se detecta transición:

→ esperar 1–2 frames posteriores más estables.

---

# **5️⃣ Flujo Técnico Propuesto**

```py
def extract_representative_frames(video):

    base_frames = uniform_sampling(video)

    filtered_frames = []

    for frame in base_frames:

        if is_stable(frame) and not is_redundant(frame, filtered_frames):
            filtered_frames.append(frame)

    return filtered_frames
```

---

# **6️⃣ Objetivo Cuantitativo**

Para video típico de 2 minutos:

Queremos terminar con:

```
Entre 15 y 25 frames finales
```

Eso es ideal para:

* Contexto suficiente  
* Token controlado  
* Cobertura total

---

# **7️⃣ Métricas de Calidad**

Después de implementar esta etapa debemos medir:

* Cantidad promedio de frames enviados.  
* Cantidad de pallets correctamente detectados.  
* Casos de pallets omitidos.  
* Tokens promedio por llamada.

---

# **8️⃣ Beneficios Directos**

* Mayor precisión en detección global.  
* Mejor lectura de etiquetas.  
* Menor redundancia.  
* Menor ruido en el prompt.  
* Mayor estabilidad del sistema.

---

# **9️⃣ Impacto Estratégico**

Con esta optimización:

El sistema pasa de ser:

Simplemente “1 llamada por video”

a ser:

1 llamada por video con curaduría inteligente de información.

Eso es arquitectura sólida.

---

# **🔟 Estado del Sistema Tras Etapa 5**

Ahora el sistema:

* Hace 1 llamada.  
* Con frames optimizados.  
* Con JSON minimalista.  
* Con integración completa.  
* Con reporte estructurado.

La versión 2.0 ya es funcional.

Perfecto.  
Entonces formalizamos la **ETAPA 6 definitiva con umbral configurable por CLI**, pensado ya con mentalidad productiva.

---

## **ETAPA 6 — Confidence-Gated Visual Fallback (Configuración por CLI)**

---

# **1️⃣ Objetivo**

Incorporar un sistema de fallback visual real que se active de manera automática cuando la confianza de Gemini esté por debajo de un umbral configurable.

El sistema debe:

* Mantener 1 llamada global como flujo principal.  
* Activar fallback solo en pallets necesarios.  
* Permitir ajuste dinámico del umbral sin modificar código.

---

# **2️⃣ Nuevo Parámetro CLI**

Se agrega al entry point:

```shell
python run.py video.mp4 --mode hybrid --confidence-threshold 0.70
```

### **Parámetro:**

```
--confidence-threshold
```

### **Tipo:**

float ∈ \[0,1\]

### **Valor por defecto:**

```
0.70
```

---

# **3️⃣ Flujo Actualizado del Pipeline**

```
Video
   ↓
Extracción de frames optimizados
   ↓
1 llamada Gemini (análisis global)
   ↓
Parse + validación estructural
   ↓
Instanciación de pallets
   ↓
Evaluación por pallet:
      confidence < threshold ?
           YES → ejecutar fallback visual
           NO  → aceptar resultado
   ↓
Generación de reporte final
```

---

# **4️⃣ Función de Decisión**

Implementación conceptual:

```py
def should_fallback(pallet, threshold):

    if pallet.confidence < threshold:
        return True

    if pallet.has_label and pallet.quantity is None:
        return True

    if pallet.has_label and pallet.internal_code is None:
        return True

    if not pallet.has_label and pallet.estimated_visible_boxes is None:
        return True

    return False
```

---

# **5️⃣ Estrategia de Fallback Visual**

Cuando se activa fallback:

1. Se extraen 3–5 frames representativos.  
2. Se envía prompt específico de conteo.  
3. Se obtiene estimación por frame.  
4. Se consolida usando mediana.

---

## **Prompt Fallback Definitivo**

You are analyzing a warehouse pallet in a frame.

Count the number of clearly visible boxes.  
Do not estimate hidden boxes.  
Do not guess.

Return STRICT JSON:

{  
"estimated\_count": integer,  
"confidence": float between 0 and 1  
}

Return ONLY JSON.

---

# **6️⃣ Consolidación de Conteos**

Ejemplo:

```
Frame1 → 12
Frame2 → 13
Frame3 → 12
```

Resultado:

```
final_quantity = median([12,13,12]) = 12
final_confidence = average(confidences)
```

---

# **7️⃣ Política de Prioridad**

Si el pallet tenía:

* Código interno leído con confianza \> threshold  
* Pero quantity con baja confianza

Entonces:

* Se conserva internal\_code  
* Se reemplaza quantity con fallback

Esto evita perder metadata válida.

---

# **8️⃣ Estructura Final de Reporte**

Ejemplo final:

```json
{
  "pallet_id": "P4",
  "internal_code": "10145317",
  "quantity": 14,
  "source": "visual_fallback",
  "fallback_used": true,
  "confidence": 0.82
}
```

---

# **9️⃣ Impacto Arquitectónico**

Con esta etapa:

* El sistema es resiliente.  
* No depende ciegamente del modelo global.  
* Permite ajuste fino según entorno real.  
* Se puede calibrar según cliente o depósito.

---

# **🔟 Estado Actual del Sistema (Post Etapa 6\)**

La versión 2.0 ahora es:

✅ 1 llamada global por video  
✅ Frames optimizados  
✅ Prompt minimalista  
✅ Parse y validación robusta  
✅ Fallback real por pallet  
✅ Umbral configurable  
✅ Reporte pallet-level

---

## **ETAPA 7 — Capa de Servidor y Endpoints (API Inventory Processing)**

---

## **1️⃣ Objetivo**

Implementar una capa de servidor que exponga el motor de inventario como un servicio, permitiendo:

* Procesar videos vía API.  
* Elegir modo (`legacy` o `hybrid`) por request.  
* Configurar `confidence_threshold` por request.  
* Consultar estado y resultados.  
* Mantener trazabilidad y manejo de errores.

El CLI sigue existiendo, pero la API pasa a ser el canal principal de integración.

---

## **2️⃣ Principios de Diseño**

* **Backward compatible:** CLI y API conviven.  
* **Asíncrono por naturaleza:** procesar un video es una tarea “larga” → endpoints basados en jobs.  
* **Idempotencia y trazabilidad:** cada corrida queda registrada.  
* **Estructura enterprise:** estados, errores tipificados, logs, artefactos.

---

## **3️⃣ Arquitectura Propuesta**

```
Client (UI / Integración / Operador)
   ↓ HTTP
API Server
   ↓
Job Queue / Worker (mismo repo, separado por rol)
   ↓
Inventory Engine (HybridInventoryPipeline / LegacyVisualPipeline)
   ↓
Storage (output artifacts + report JSON/CSV)
```

---

## **4️⃣ Contratos API (Endpoints)**

### **4.1 Crear Job de Procesamiento**

**POST** `/api/v1/inventory/jobs`

**Body (multipart/form-data)**

* `video`: archivo  
* `mode`: `legacy | hybrid` (default: legacy)  
* `confidence_threshold`: float 0–1 (default: 0.70, solo aplica a hybrid)  
* `frames_strategy`: `optimized` (default) *(opcional, para futuro)*  
* `metadata`: json opcional (cliente, depósito, pasillo, operador)

**Response 202**

```json
{
  "job_id": "job_20260303_0001",
  "status": "queued",
  "mode": "hybrid",
  "confidence_threshold": 0.7
}
```

---

### **4.2 Consultar Estado de Job**

**GET** `/api/v1/inventory/jobs/{job_id}`

**Response 200**

```json
{
  "job_id": "job_20260303_0001",
  "status": "running",
  "progress": {
    "stage": "gemini_global_call",
    "percent": 55
  },
  "created_at": "2026-03-03T10:12:00-03:00"
}
```

Estados posibles:

* `queued`  
* `running`  
* `succeeded`  
* `failed`  
* `canceled` *(si lo implementamos más adelante)*

---

### **4.3 Obtener Resultado Final**

**GET** `/api/v1/inventory/jobs/{job_id}/result`

**Response 200**

```json
{
  "job_id": "job_20260303_0001",
  "status": "succeeded",
  "report": {
    "video_id": "…",
    "mode": "hybrid",
    "confidence_threshold": 0.7,
    "pallets": [
      {
        "pallet_id": "P1",
        "internal_code": "10145317",
        "quantity": 15,
        "source": "label",
        "confidence": 0.94,
        "fallback_used": false
      }
    ]
  }
}
```

---

### **4.4 Descargar Artefactos**

**GET** `/api/v1/inventory/jobs/{job_id}/artifacts`

Devuelve links o lista:

* `report.json`  
* `report.csv`  
* `selected_frames/`  
* `fallback_frames/` *(si se activó)*  
* `debug/` *(si está habilitado)*

---

### **4.5 Healthcheck**

**GET** `/health`

**Response 200**

```json
{ "ok": true }
```

---

## **5️⃣ Modelo de Job Interno**

Estructura sugerida:

```json
{
  "job_id": "job_...",
  "input": {
    "video_path": "...",
    "mode": "hybrid",
    "confidence_threshold": 0.7
  },
  "status": "running",
  "progress": { "stage": "...", "percent": 0 },
  "output": {
    "report_json_path": "...",
    "report_csv_path": "...",
    "artifacts_dir": "..."
  },
  "error": null
}
```

---

## **6️⃣ Organización del Repo (Propuesta)**

```
src/
  api/
    server.py
    routes/
      jobs.py
    schemas/
      requests.py
      responses.py

  jobs/
    queue.py
    worker.py
    job_store.py

  pipeline/
    hybrid_pipeline.py
    visual_advanced.py

  output/
    <job_id>/
      report.json
      report.csv
      frames_selected/
      frames_fallback/
```

---

## **7️⃣ Criterios de Éxito de la Etapa 7**

* API crea jobs y no se bloquea.  
* Se puede consultar progreso.  
* Se obtiene resultado estructurado.  
* Se guardan artefactos por job.  
* `mode` y `confidence_threshold` funcionan igual que CLI.  
* Legacy sigue operativo.

---

## **8️⃣ Seguridad y Operación (mínimo viable)**

* API Key simple por header (fase 1).  
* Límite de tamaño de archivo.  
* Timeouts y manejo de errores.  
* Logs estructurados por job\_id.

---

## **9️⃣ Estado del Sistema Tras Etapa 7**

Con esta etapa, Dinamic pasa de “herramienta” a “producto integrable”:

* Integración con dashboard  
* Integración con WMS/ERP  
* Escalabilidad a workers múltiples

---

## **ETAPA 8 — Persistencia en Base de Datos (Jobs, Resultados y Auditoría)**

---

## **1️⃣ Objetivo**

Incorporar una capa de persistencia para:

* Registrar jobs creados por API/CLI.  
* Mantener estado y progreso de cada ejecución.  
* Guardar resultados estructurados por pallet.  
* Versionar parámetros y configuración utilizada.  
* Permitir re-procesamiento, auditoría y consultas históricas.

La API deja de depender del filesystem como “fuente de verdad”.

---

## **2️⃣ Principios de Diseño**

* **DB como fuente de verdad:** estado y resultados viven en DB.  
* **Artifacts en storage:** archivos pesados (frames, CSV, debug) quedan en disco o storage externo, referenciados por DB.  
* **Trazabilidad completa:** cada job registra inputs, configuración, outputs y errores.  
* **Compatibilidad:** CLI y API usan el mismo modelo de persistencia.

---

## **3️⃣ Modelo de Datos Propuesto**

### **3.1 Tabla: `jobs`**

Registra el ciclo completo del procesamiento.

Campos sugeridos:

* `id` (PK, string/uuid)  
* `created_at`  
* `updated_at`  
* `status` (`queued|running|succeeded|failed|canceled`)  
* `mode` (`legacy|hybrid`)  
* `confidence_threshold` (float)  
* `video_filename` (string)  
* `video_path` (string) *(o storage uri)*  
* `frames_count_sent` (int)  
* `gemini_calls` (int) *(en v2 debería ser 1 \+ fallbacks)*  
* `progress_stage` (string)  
* `progress_percent` (int)  
* `error_code` (string|null)  
* `error_message` (string|null)  
* `artifacts_dir` (string|null)  
* `report_json_path` (string|null)  
* `report_csv_path` (string|null)  
* `engine_version` (string) *(ej: “v2.0”)*  
* `prompt_version` (string) *(ej: “global\_min\_v1”)*  
* `metadata` (json) *(cliente, depósito, pasillo, operador)*

---

### **3.2 Tabla: `pallet_results`**

Un registro por pallet detectado.

Campos:

* `id` (PK)  
* `job_id` (FK jobs.id)  
* `pallet_id` (string, ej “P1”)  
* `internal_code` (string|null)  
* `quantity` (int|null)  
* `source` (`label|visual_fallback|legacy`)  
* `confidence` (float|null)  
* `fallback_used` (bool)  
* `raw_estimated_visible_boxes` (int|null)  
* `created_at`

---

### **3.3 Tabla: `job_events` (auditoría / timeline)**

Log estructurado de eventos relevantes.

Campos:

* `id` (PK)  
* `job_id` (FK)  
* `timestamp`  
* `event_type` (string) *(ej: “FRAMES\_SELECTED”, “GEMINI\_CALL”, “FALLBACK\_RUN”, “REPORT\_WRITTEN”)*  
* `payload` (json) *(detalles: cantidad de frames, tokens estimados, etc.)*

Esta tabla es clave para debugging enterprise.

---

## **4️⃣ Flujo Operativo con Persistencia**

### **Al crear job:**

* Insert en `jobs` con status `queued`.

### **Al iniciar worker:**

* Update `jobs.status = running`  
* Update progreso por etapa.

### **Al completar análisis global:**

* Guardar métricas:  
  * frames enviados  
  * gemini calls  
* Insertar `pallet_results` por pallet.

### **Al finalizar:**

* status `succeeded`  
* registrar paths de artefactos  
* registrar event timeline

### **Si falla:**

* status `failed`  
* error\_code \+ error\_message  
* registrar evento de error

---

## **5️⃣ Integración con la API (Endpoints)**

La API pasa a leer estado/resultados desde DB:

* `GET /jobs/{id}` → `jobs`  
* `GET /jobs/{id}/result` → `pallet_results` \+ metadata job  
* `GET /jobs/{id}/events` *(opcional)* → `job_events`

---

## **6️⃣ Integración con CLI (Convivencia)**

El CLI, cuando se ejecuta localmente, puede:

* Insertar un job en DB como “manual\_run”  
* O correr sin DB (modo offline) — *pero recomendado usar DB siempre*

Para v2.0 profesional, recomendado:

CLI también crea jobs en DB para mantener trazabilidad uniforme.

---

## **7️⃣ Estrategia de Storage de Artefactos**

DB no guarda binarios.

Artefactos quedan en:

* `output/<job_id>/...`

DB guarda:

* `artifacts_dir`  
* `report_json_path`  
* `report_csv_path`

En futuro se puede migrar a S3/GCS sin romper DB.

---

## **8️⃣ Criterios de Éxito de la Etapa 8**

* Cada job queda persistido con su estado final.  
* Resultados por pallet consultables por API.  
* Errores quedan registrados y auditables.  
* Logs de eventos permiten debugging sin abrir archivos.  
* Reproducibilidad: se guardan `engine_version` y `prompt_version`.

---

## **9️⃣ Estados y Reglas de Consistencia**

Reglas recomendadas:

* `succeeded` implica `report_json_path != null`  
* `failed` implica `error_code != null`  
* `running` debe tener `progress_stage` seteado  
* `pallet_results.job_id` debe existir siempre

---

## **🔟 Próximas Extensiones (no incluidas aún)**

* Multi-tenant (clientes, depósitos)  
* Usuarios y roles  
* Reintentos automáticos  
* Cancelación real de jobs  
* Dashboard / UI para visualizar jobs

---

## **1️⃣1️⃣ Resultado Estratégico**

Con Etapa 8:

* La API se vuelve robusta y productizable.  
* Se habilita histórico y trazabilidad.  
* Se habilita integración enterprise real.

:

---

# **📦 Cierre Formal de Version 2.0**

Hasta ahora la v2.0 incluye:

1️⃣ Reestructuración del core (convivencia legacy \+ hybrid)  
 2️⃣ Modelo single-call por video  
 3️⃣ Prompt global minimalista  
 4️⃣ Integración operativa  
 5️⃣ Optimización de selección de frames  
 6️⃣ Fallback real por confianza configurable  
 7️⃣ API con endpoints  
 8️⃣ Persistencia en DB  
 9️⃣ Robustez básica (reintentos \+ idempotencia \+ concurrencia mínima)

Esto ya es una versión sólida y entregable.

---

# **🔜 Version 2.1 — Roadmap Futuro (Separado)**

Para que quede profesional, definimos que 2.1 incluirá:

* Multi-worker real

* Escalabilidad horizontal

* Observabilidad avanzada (metrics \+ tracing)

* Control de costos por job

* Autenticación y roles

* Rate limiting

* Gobernanza de prompts/versionado

* Optimización avanzada de performance

Eso ya es otra etapa de madurez.

---

# **🎯 Conclusión Estratégica**

La v2.0 ahora:

* Es funcional

* Es coherente

* Es minimalista en arquitectura

* Tiene fallback

* Tiene API

* Tiene DB

* Tiene robustez básica

No está sobredimensionada.

