# 📋 Plan de Implementación - Sistema de Inventario por Video + Gemini

## 📌 Información General

**Proyecto:** Sistema de Conteo de Inventario por Video  
**Tecnología:** Python 3.9+ con Gemini API  
**Fecha de creación:** 2024  
**Estado:** Planificación

---

## 🎯 Objetivo del Plan

Implementar un sistema MVP funcional que procese videos de depósito, extraiga frames, consulte la API de Gemini para conteo de cajas por pallet, y genere un JSON estructurado con resultados consolidados.

---

## 📊 Fases de Implementación

### **Fase 0: Setup y Configuración Inicial** ⚙️
**Duración estimada:** 1-2 días  
**Prioridad:** 🔴 Crítica

#### Tareas:
- [ ] **0.1** Crear estructura de carpetas del proyecto
  - [ ] `src/` con subdirectorios
  - [ ] `tests/`
  - [ ] `output/`
  - [ ] `configs/`
  - [ ] `data/` (para videos de prueba)

- [ ] **0.2** Configurar entorno de desarrollo
  - [ ] Crear `pyproject.toml` con dependencias
  - [ ] Configurar `poetry` o `pip` + `requirements.txt`
  - [ ] Crear `.env.example` con variables de entorno
  - [ ] Configurar `.gitignore`

- [ ] **0.3** Dependencias principales
  ```toml
  - pydantic >= 2.0.0
  - opencv-python >= 4.8.0
  - google-generativeai >= 0.3.0
  - python-dotenv >= 1.0.0
  - pytest >= 7.4.0 (dev)
  - black, ruff (dev)
  ```

- [ ] **0.4** Crear `README.md` básico
  - [ ] Instrucciones de instalación
  - [ ] Configuración de API key
  - [ ] Ejemplo de uso mínimo

**Criterios de completitud:**
- ✅ Proyecto se puede instalar con `pip install -e .`
- ✅ Variables de entorno se cargan correctamente
- ✅ Estructura de carpetas creada

---

### **Fase 1: Modelos de Datos (Schemas)** 📐
**Duración estimada:** 1 día  
**Prioridad:** 🔴 Crítica  
**Dependencias:** Fase 0

#### Tareas:
- [ ] **1.1** Implementar `src/models/schemas.py`
  - [ ] Helper `clamp01()`
  - [ ] Modelos minificados: `MinifiedProduct`, `MinifiedPallet`, `MinifiedFrameResult`
  - [ ] Modelos de metadata: `VideoMetadata`, `FrameRef`
  - [ ] Modelos de salida: `ProductEstimate`, `PalletEstimate`, `FinalResult`
  - [ ] Modelos internos: `LLMProductObservation`, `LLMPalletObservation`, `LLMFrameResult`
  - [ ] Modelos de consolidación: `ConsolidationStats`, `ConsolidatedProduct`, `ConsolidatedPallet`, `ConsolidatedResult`

- [ ] **1.2** Validaciones
  - [ ] Validadores de confianza (0-1)
  - [ ] Validadores de campos numéricos (ge=0, gt=0)
  - [ ] ConfigDict con `extra="forbid"`

- [ ] **1.3** Tests unitarios básicos
  - [ ] Test de creación de modelos válidos
  - [ ] Test de validación de confianza
  - [ ] Test de serialización JSON

**Criterios de completitud:**
- ✅ Todos los modelos Pydantic definidos
- ✅ Validaciones funcionan correctamente
- ✅ Tests pasan (cobertura > 80%)

---

### **Fase 2: Configuración y Utilidades** ⚙️
**Duración estimada:** 0.5 días  
**Prioridad:** 🔴 Crítica  
**Dependencias:** Fase 0

#### Tareas:
- [ ] **2.1** Implementar `src/config.py`
  - [ ] Clase `Settings` con Pydantic
  - [ ] Carga de variables de entorno
  - [ ] Valores por defecto sensatos
  - [ ] Función `load_settings()`

- [ ] **2.2** Crear `.env.example`
  ```env
  GEMINI_API_KEY=your_api_key_here
  MAX_FRAMES_TO_SEND=10
  EXTRACT_FPS=1.0
  RESIZE_MAX_SIDE=1280
  OUTPUT_DIR=output
  DEBUG_SAVE_FRAMES=false
  ```

- [ ] **2.3** Tests de configuración
  - [ ] Test de carga desde env
  - [ ] Test de valores por defecto

**Criterios de completitud:**
- ✅ Configuración se carga correctamente
- ✅ Variables de entorno funcionan
- ✅ Tests pasan

---

### **Fase 3: Módulo de Video** 🎥
**Duración estimada:** 2 días  
**Prioridad:** 🔴 Crítica  
**Dependencias:** Fases 1, 2

#### Tareas:
- [ ] **3.1** Implementar `src/video/ingest.py`
  - [ ] Función `load_video_metadata(video_path: str) -> VideoMetadata`
  - [ ] Validación de existencia de archivo
  - [ ] Validación de formato soportado
  - [ ] Extracción de metadata (fps, duración, resolución)
  - [ ] Manejo de errores (archivo corrupto, formato no soportado)

- [ ] **3.2** Implementar `src/video/frames.py`
  - [ ] Función `extract_frames(video_path: str, target_fps: float) -> List[FrameRef]`
  - [ ] Muestreo por FPS objetivo
  - [ ] Generación de `FrameRef` con metadata
  - [ ] Manejo de videos vacíos o corruptos

- [ ] **3.3** Tests del módulo de video
  - [ ] Test con video de prueba
  - [ ] Test de extracción de frames
  - [ ] Test de cálculo de timestamps
  - [ ] Test de manejo de errores

**Criterios de completitud:**
- ✅ Se puede cargar metadata de video
- ✅ Se extraen frames correctamente
- ✅ Frames tienen timestamps y índices correctos
- ✅ Tests pasan con videos de prueba

---

### **Fase 4: Preprocesamiento de Imágenes** 🖼️
**Duración estimada:** 2 días  
**Prioridad:** 🟡 Alta  
**Dependencias:** Fase 3

#### Tareas:
- [ ] **4.1** Implementar `src/preprocess/image_ops.py`
  - [ ] Función `resize_image(frame: np.ndarray, max_side: int) -> np.ndarray`
  - [ ] Función `apply_roi(frame: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray`
  - [ ] Función `compress_image(frame: np.ndarray, quality: int) -> bytes`
  - [ ] Función `save_frame(frame: np.ndarray, output_path: str) -> str`
  - [ ] Función `load_frame(image_path: str) -> np.ndarray`

- [ ] **4.2** Implementar `src/preprocess/selectors.py`
  - [ ] Función `select_frames(frames: List[FrameRef], max_frames: int, strategy: str) -> List[FrameRef]`
  - [ ] Estrategias: `uniform`, `first_n`, `distributed`
  - [ ] Función `prepare_frames_for_api(frames: List[FrameRef], video_path: str, output_dir: str) -> List[str]`
    - Guarda frames seleccionados a disco
    - Retorna lista de paths

- [ ] **4.3** Función helper para Gemini
  - [ ] `path_to_gemini_part(image_path: str) -> Part` (o equivalente según SDK)
  - [ ] Conversión de imagen a formato compatible con Gemini API

- [ ] **4.4** Tests de preprocesamiento
  - [ ] Test de redimensionado
  - [ ] Test de selección de frames
  - [ ] Test de guardado de frames

**Criterios de completitud:**
- ✅ Frames se redimensionan correctamente
- ✅ Selección de frames funciona
- ✅ Frames se guardan y cargan correctamente
- ✅ Función de conversión para Gemini funciona

---

### **Fase 5: Integración con Gemini API** 🤖
**Duración estimada:** 3-4 días  
**Prioridad:** 🔴 Crítica  
**Dependencias:** Fases 1, 2, 4

#### Tareas:
- [ ] **5.1** Implementar `src/llm/prompts.py`
  - [ ] `SYSTEM_PROMPT_PALLET_COUNT`
  - [ ] `USER_PROMPT_PALLET_COUNT`
  - [ ] Función `get_prompt_profile(profile_name: str) -> Dict[str, str]`
  - [ ] Preparar estructura para múltiples perfiles

- [ ] **5.2** Implementar `src/llm/gemini_client.py`
  - [ ] Clase `GeminiClient`
    - [ ] `__init__(api_key: str, model_name: str)`
    - [ ] Inicialización del cliente real de Gemini
  - [ ] Método `analyze_frames(frames: List[FrameRef], image_paths: List[str]) -> List[LLMFrameResult]`
    - [ ] Generación de schema JSON desde Pydantic
    - [ ] Construcción de request con system instruction
    - [ ] Envío de cada frame a Gemini
    - [ ] Parseo de respuesta JSON minificada
    - [ ] Mapeo a modelos internos (`LLMProductObservation`, etc.)
    - [ ] Manejo de errores y excepciones

- [ ] **5.3** Manejo de errores y reintentos
  - [ ] Implementar retry con backoff exponencial
  - [ ] Manejo de rate limits (429)
  - [ ] Implementar RF-07: "repair JSON" cuando respuesta no es JSON válido
    - [ ] Detectar respuesta no-JSON
    - [ ] Reintentar con prompt de reparación
    - [ ] Fallback si falla reparación

- [ ] **5.4** Tests de integración con Gemini
  - [ ] Test con mock de Gemini API
  - [ ] Test de parseo de respuesta JSON
  - [ ] Test de manejo de errores
  - [ ] Test de retry logic
  - [ ] Test end-to-end con video pequeño (opcional, requiere API key)

**Criterios de completitud:**
- ✅ Cliente Gemini se inicializa correctamente
- ✅ Se envían frames y se reciben respuestas
- ✅ JSON se parsea correctamente
- ✅ Manejo de errores funciona
- ✅ Tests pasan (con mocks)

---

### **Fase 6: Consolidación de Resultados** 📊
**Duración estimada:** 2-3 días  
**Prioridad:** 🔴 Crítica  
**Dependencias:** Fases 1, 5

#### Tareas:
- [ ] **6.1** Implementar `src/consolidate/normalize.py`
  - [ ] Función `normalize_product_key(brand: Optional[str], product: str) -> str`
  - [ ] Normalización de strings (lowercase, trim, etc.)

- [ ] **6.2** Implementar `src/consolidate/consolidate.py`
  - [ ] Función helper `_mad(xs: List[int], med: float) -> float`
  - [ ] Función `consolidate(video_id: str, frame_results: List[LLMFrameResult], n_target: int = 8) -> ConsolidatedResult`
    - [ ] Agrupación por `pallet_id` y `product_key`
    - [ ] Cálculo de mediana y MAD
    - [ ] Filtrado de outliers (inliers)
    - [ ] Cálculo de estimación final (mediana de inliers)
    - [ ] Cálculo de confianza final (con stability_factor y coverage_factor)
    - [ ] Generación de `ConsolidationStats`
    - [ ] Construcción de `ConsolidatedResult`

- [ ] **6.3** Tests de consolidación
  - [ ] Test con datos sintéticos
  - [ ] Test de cálculo de MAD
  - [ ] Test de filtrado de outliers
  - [ ] Test de cálculo de confianza
  - [ ] Test con múltiples frames del mismo pallet
  - [ ] Test edge cases (un solo frame, frames con valores idénticos)

**Criterios de completitud:**
- ✅ Consolidación agrupa correctamente
- ✅ MAD y filtrado de outliers funcionan
- ✅ Confianza se calcula correctamente
- ✅ Tests pasan con casos variados

---

### **Fase 7: I/O y Exportación** 💾
**Duración estimada:** 1-2 días  
**Prioridad:** 🟡 Alta  
**Dependencias:** Fases 1, 6

#### Tareas:
- [ ] **7.1** Implementar `src/io/outputs.py`
  - [ ] Función `to_final_result(consolidated: ConsolidatedResult) -> FinalResult`
  - [ ] Función `save_result(result: FinalResult, output_path: str) -> None`
  - [ ] Función `save_result_json(result: FinalResult, output_path: str) -> None`
  - [ ] Función `print_summary(result: FinalResult) -> None`

- [ ] **7.2** Implementar `src/io/logging.py`
  - [ ] Configuración de logging estructurado
  - [ ] Función `setup_logger(output_dir: str, run_id: str) -> Logger`
  - [ ] Logging de métricas:
    - [ ] Tiempos por etapa
    - [ ] Cantidad de frames procesados
    - [ ] Errores y reintentos
    - [ ] Tamaño de datos enviados (si es posible)

- [ ] **7.3** Tests de I/O
  - [ ] Test de guardado de JSON
  - [ ] Test de conversión a FinalResult
  - [ ] Test de logging

**Criterios de completitud:**
- ✅ Resultados se guardan en JSON válido
- ✅ Logging funciona correctamente
- ✅ Resumen se imprime en consola

---

### **Fase 8: CLI y Orquestación** 🎮
**Duración estimada:** 2 días  
**Prioridad:** 🔴 Crítica  
**Dependencias:** Todas las fases anteriores

#### Tareas:
- [ ] **8.1** Implementar `src/app.py` o `src/cli.py`
  - [ ] Función `main()` con argparse
  - [ ] Argumentos CLI:
    - [ ] `--video` (requerido)
    - [ ] `--video-id` (opcional)
    - [ ] `--fps` / `--extract-fps`
    - [ ] `--max-frames`
    - [ ] `--resize` / `--resize-max-side`
    - [ ] `--profile` (opcional)
    - [ ] `--output` / `--output-dir`
    - [ ] `--debug` (flag para guardar frames)
  - [ ] Orquestación del pipeline completo:
    1. Cargar configuración
    2. Validar video
    3. Extraer frames
    4. Seleccionar y preprocesar frames
    5. Enviar a Gemini
    6. Consolidar resultados
    7. Exportar JSON
    8. Mostrar resumen

- [ ] **8.2** Manejo de errores en CLI
  - [ ] Mensajes de error claros
  - [ ] Exit codes apropiados
  - [ ] Validación de argumentos

- [ ] **8.3** Tests de CLI
  - [ ] Test de parsing de argumentos
  - [ ] Test de ejecución completa (con mocks)
  - [ ] Test de manejo de errores

**Criterios de completitud:**
- ✅ CLI funciona con todos los argumentos
- ✅ Pipeline completo se ejecuta
- ✅ Manejo de errores es robusto
- ✅ Tests pasan

---

### **Fase 9: Testing y Validación** ✅
**Duración estimada:** 2-3 días  
**Prioridad:** 🟡 Alta  
**Dependencias:** Fase 8

#### Tareas:
- [ ] **9.1** Tests de integración end-to-end
  - [ ] Test completo con video de prueba pequeño
  - [ ] Validar output JSON
  - [ ] Validar estructura de datos

- [ ] **9.2** Tests de casos edge
  - [ ] Video vacío
  - [ ] Video corrupto
  - [ ] Sin pallets detectados
  - [ ] Múltiples pallets
  - [ ] Un solo frame

- [ ] **9.3** Validación con datos reales (si disponibles)
  - [ ] Probar con videos reales de depósito
  - [ ] Comparar con ground truth (si existe)
  - [ ] Medir error promedio

- [ ] **9.4** Performance testing
  - [ ] Medir tiempo de procesamiento
  - [ ] Identificar cuellos de botella
  - [ ] Optimizar si es necesario

**Criterios de completitud:**
- ✅ Tests end-to-end pasan
- ✅ Casos edge manejados
- ✅ Performance aceptable (< 60s para video de 2 min)

---

### **Fase 10: Documentación y Pulido** 📚
**Duración estimada:** 1-2 días  
**Prioridad:** 🟢 Media  
**Dependencias:** Fase 9

#### Tareas:
- [ ] **10.1** Actualizar `README.md`
  - [ ] Descripción del proyecto
  - [ ] Instrucciones de instalación completas
  - [ ] Configuración de API key
  - [ ] Ejemplos de uso
  - [ ] Estructura del proyecto
  - [ ] Troubleshooting

- [ ] **10.2** Documentación de código
  - [ ] Docstrings en todas las funciones públicas
  - [ ] Type hints completos
  - [ ] Comentarios en código complejo

- [ ] **10.3** Crear `CONTRIBUTING.md` (opcional)
  - [ ] Guía de desarrollo
  - [ ] Estándares de código
  - [ ] Proceso de testing

- [ ] **10.4** Crear `CHANGELOG.md`
  - [ ] Versión inicial
  - [ ] Features implementadas

**Criterios de completitud:**
- ✅ README completo y claro
- ✅ Código documentado
- ✅ Ejemplos funcionan

---

## 📈 Orden de Implementación Recomendado

```
Fase 0 (Setup)
    ↓
Fase 1 (Schemas) ──┐
    ↓              │
Fase 2 (Config) ───┤
    ↓              │
Fase 3 (Video) ────┼──→ Fase 4 (Preprocess)
    ↓              │         ↓
    └──────────────┴─────────┴──→ Fase 5 (Gemini)
                                    ↓
                              Fase 6 (Consolidate)
                                    ↓
                              Fase 7 (I/O)
                                    ↓
                              Fase 8 (CLI)
                                    ↓
                              Fase 9 (Testing)
                                    ↓
                              Fase 10 (Docs)
```

---

## 🎯 Criterios de Éxito del MVP

El MVP se considera completo cuando:

- ✅ **Funcionalidad básica:**
  - [ ] Procesa video y extrae frames
  - [ ] Consulta Gemini API correctamente
  - [ ] Genera `result.json` válido
  - [ ] Contiene pallets, productos, conteos y confianza

- ✅ **Calidad:**
  - [ ] JSON válido 100% de las veces
  - [ ] Manejo robusto de errores
  - [ ] Logs disponibles

- ✅ **Testing:**
  - [ ] Tests unitarios > 70% cobertura
  - [ ] Tests de integración pasan
  - [ ] Casos edge manejados

- ✅ **Documentación:**
  - [ ] README completo
  - [ ] Código documentado
  - [ ] Ejemplos funcionan

---

## ⚠️ Riesgos y Mitigaciones

| Riesgo | Impacto | Probabilidad | Mitigación |
|--------|---------|--------------|------------|
| API de Gemini cambia | Alto | Media | Usar versiones fijas del SDK, tests con mocks |
| Costos de API altos | Medio | Alta | Limitar frames, comprimir imágenes, monitorear uso |
| Variabilidad en conteos | Alto | Alta | Consolidación robusta (MAD), múltiples frames |
| Videos corruptos | Medio | Media | Validación temprana, manejo de errores |
| Performance lenta | Medio | Media | Optimizar extracción, procesamiento paralelo (futuro) |

---

## 📝 Notas de Implementación

### Decisiones Técnicas

1. **Pydantic v2:** Usar para validación estricta y serialización
2. **OpenCV:** Para procesamiento de video (estándar de la industria)
3. **Gemini 2.5 Flash:** Modelo recomendado para visión rápida
4. **MAD para outliers:** Más robusto que desviación estándar
5. **Mediana para estimación:** Más estable que promedio para conteos discretos

### Consideraciones de Costo

- Limitar `max_frames_to_send` (default: 10)
- Redimensionar imágenes (default: 1280px)
- Usar modelos minificados en JSON
- Comprimir imágenes antes de enviar

### Extensiones Futuras (Post-MVP)

- Detección de cambios de escena
- Tracking multi-objeto
- Integración con YOLO
- Procesamiento paralelo
- API REST
- Dashboard web

---

## 📅 Estimación Total

**Duración estimada del MVP:** 18-25 días hábiles (3.5-5 semanas)

**Desglose:**
- Setup: 1-2 días
- Desarrollo core: 12-16 días
- Testing: 2-3 días
- Documentación: 1-2 días
- Buffer: 2-3 días

---

## 🔄 Actualización del Plan

Este plan debe actualizarse según:
- Cambios en requerimientos
- Bloqueos encontrados
- Nuevas dependencias identificadas
- Feedback de pruebas

**Última actualización:** [Fecha]

---

## ✅ Checklist de Inicio

Antes de comenzar, asegurar:

- [ ] Repositorio creado
- [ ] Entorno de desarrollo configurado
- [ ] API key de Gemini obtenida
- [ ] Videos de prueba disponibles (opcional)
- [ ] Acceso a documentación de Gemini API
- [ ] Herramientas de desarrollo instaladas (Python, git, etc.)

---

**Fin del Plan de Implementación**
