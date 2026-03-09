# Arquitectura del sistema — Versión 2.3

**Documento de referencia técnica**  
Sistema de inventario por visión (video/fotos) con pipeline híbrido y análisis global por LLM.

---

## 1. Resumen ejecutivo

La versión 2.3 introduce una **arquitectura por etapas (stages)** y **puertos y adaptadores (Ports & Adapters)** sobre el flujo híbrido existente. El pipeline de inventario queda dividido en etapas explícitas con contratos bien definidos, contexto de ejecución centralizado y abstracciones para el análisis LLM, el almacenamiento de trabajos y el almacenamiento de artefactos. El comportamiento observable (formato de reporte, rutas de artefactos, API y worker) se mantiene compatible con versiones anteriores.

**Principios:**

- **Contexto de ejecución único:** `RunContext` lleva identificación del run, rutas, configuración y logger; no se usa para resultados intermedios entre etapas.
- **Contratos por etapa:** Cada etapa recibe `RunContext` + datos de la etapa anterior y devuelve un DTO tipado.
- **Orquestador fino:** El orquestador solo encadena etapas, reporta progreso y mapea fallos a códigos de salida.
- **Puertos preparatorios:** Los puertos de jobs, cola y almacenamiento de artefactos están definidos y documentados; la integración en worker/API queda para fases posteriores.

---

## 2. Contexto y evolución

| Versión | Cambio principal |
|--------|--------------------|
| 2.1 | Análisis global por LLM (schema v2.1), entidades, reporte híbrido. |
| 2.2 | FrameSource (video/fotos), normalización de fotos, FakeProvider, API de jobs. |
| 2.3.A | RunContext, contrato PipelineStage, InputPreparationStage. |
| 2.3.B | Puertos: AnalysisProvider, JobRepository, JobQueue, ArtifactStorage; adaptadores sobre implementaciones actuales. |
| 2.3.C | Pipeline descompuesto en seis etapas; orquestador fino; alineación de frames y manejo de errores unificado. |

---

## 3. Arquitectura del pipeline (V2.3)

### 3.1 Flujo de alto nivel

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                  HybridInventoryPipeline                 │
                    │  process_video() → _run_hybrid() (orquestador)          │
                    └─────────────────────────────────────────────────────────┘
                                                      │
         ┌────────────────────────────────────────────┼────────────────────────────────────────────┐
         ▼                                            ▼                                            ▼
┌─────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────┐
│InputPreparation │→ │FrameAcquisition     │→ │Analysis             │→ │EntityResolution     │→ │Evidence         │→ Reporting
│Stage            │  │Stage                │  │Stage                │  │Stage                │  │Stage            │
└─────────────────┘  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘  └─────────────────┘
       │                        │                        │                        │                        │
       ▼                        ▼                        ▼                        ▼                        ▼
 PreparedInput           AcquiredFrames          AnalysisStageResult      ResolvedEntities        EvidenceArtifacts
                         (frames_nd, paths,      (parsed_json,            (entities con           (evidence_index)
                          metadata, refs         provider_name)            status/quality)
                          alineados)
```

### 3.2 RunContext (Stage A)

**Ubicación:** `src/pipeline/context/run_context.py`

`RunContext` es el **contexto de ejecución** de un run del pipeline. Contiene únicamente:

- Identificación: `job_id`, `run_id`
- Rutas: `workspace_path`, `run_dir`
- Entrada del job: `job_input` (JobInput)
- Configuración: `settings`
- Logger y callback de progreso
- Diccionario `metadata` para trazabilidad (no para resultados de etapas)

**Regla:** Los resultados de cada etapa **no** se guardan en `RunContext`; fluyen mediante los valores de retorno (DTOs).

### 3.3 Contrato PipelineStage (Stage A)

**Ubicación:** `src/pipeline/contracts/stage.py`

Todas las etapas cumplen el protocolo:

```python
def run(self, context: RunContext, data: Any) -> Any
```

- `data`: salida de la etapa anterior (`None` en la primera).
- Retorno: DTO que consume la siguiente etapa (o el orquestador en la última).

### 3.4 Etapas del pipeline (Stages A y C)

| Etapa | Módulo | Entrada | Salida | Responsabilidad |
|-------|--------|---------|--------|------------------|
| **InputPreparationStage** | `stages/input_preparation_stage.py` | `None` | `PreparedInput` | Crear `run_dir`, validar `job_input`, normalizar fotos si aplica. |
| **FrameAcquisitionStage** | `stages/frame_acquisition_stage.py` | `PreparedInput` | `AcquiredFrames` | Obtener frames vía FrameSource, cargar en RAM, devolver listas alineadas (frames_nd, paths, refs, frame_indices). |
| **AnalysisStage** | `stages/analysis_stage.py` | `AcquiredFrames` | `AnalysisStageResult` | Llamar a `AnalysisProvider.analyze()` y devolver JSON parseado y nombre del proveedor. |
| **EntityResolutionStage** | `stages/entity_resolution_stage.py` | `AnalysisStageResult` | `ResolvedEntities` | Parsear entidades v2.1, ordenar, resolver pallet_id, asignar count_status y quality score. |
| **EvidenceStage** | `stages/evidence_stage.py` | `EvidenceStageInput`* | `EvidenceArtifacts` | Generar pack de evidencia (overview + crops), escribir `evidence/` y `evidence_index.json`. |
| **ReportingStage** | `stages/reporting_stage.py` | `ReportingStageInput`* | `ReportingResult` | Construir reporte híbrido v2.1 y escribir `hybrid_report.json` en `run_dir`. |

\* `EvidenceStageInput` y `ReportingStageInput` los construye el orquestador a partir de `AcquiredFrames` y `ResolvedEntities`.

### 3.5 Alineación de frames (Stage C)

En **FrameAcquisitionStage**, si algún frame no se puede cargar (`cv2.imread` falla), solo se devuelven los cargados y **todas** las listas siguen alineadas por índice:

- `frames_nd[i]`, `frame_paths[i]`, `frame_refs[i]` y `metadata["frame_indices"][i]` corresponden al mismo frame.

Así se evitan desajustes en el análisis y en la evidencia.

### 3.6 Manejo de errores en el orquestador

Cada etapa se ejecuta dentro de un `try/except`. Cualquier fallo se registra con el mismo formato:

```text
Stage failure: <NombreEtapa> (job_id=%s): %s
```

y el orquestador devuelve código de salida **1**. El worker interpreta código distinto de 0 como fallo y actualiza el job a FAILED.

---

## 4. Puertos y adaptadores (Stage B)

### 4.1 AnalysisProvider

**Puerto:** `src/pipeline/ports/analysis_provider.py`

- **Responsabilidad:** Realizar el análisis global (entidades v2.1) a partir de frames y metadatos.
- **Método:** `analyze(context, frames_nd, frame_paths, frame_refs, metadata) → AnalysisResult`.
- **AnalysisResult:** `parsed_json` (dict v2.1) y `provider_name`.

**Adaptador actual:** `GeminiAnalysisProvider` en `src/pipeline/adapters/gemini_analysis_provider.py`. Delega en `get_llm_provider(settings)` (Gemini, OpenAI o Fake) y en el flujo existente de prompt/schema v2.1. No es un abstracción genérica de Gemini; está acotada al análisis global actual.

### 4.2 JobRepository

**Puerto:** `src/jobs/ports/job_repository.py`

- **Responsabilidad:** Persistencia de jobs (crear, obtener, actualizar).
- **Métodos:** `get(job_id)`, `update(job_id, **updates)`, `create(record)`.

**Adaptador:** `JobStoreRepositoryAdapter` sobre `job_store` (filesystem + opcional SQL Server). `create()` relee el job tras crearlo y devuelve el registro persistido cuando es posible.

**Estado:** El worker y la API siguen usando `job_store` directamente; el puerto está listo para una futura inyección.

### 4.3 JobQueue

**Puerto:** `src/jobs/ports/job_queue.py`

- **Responsabilidad:** Cola de trabajos (encolar, desencolar).
- **Métodos:** `enqueue(job_id)`, `dequeue(timeout)`.

**Adaptador:** `InMemoryJobQueue` sobre el módulo `queue` actual. Los docstrings aclaran que es un contrato mínimo y que no hay ack/nack/retry.

**Estado:** Worker usa `queue.enqueue`/`dequeue`; el puerto no está conectado aún.

### 4.4 ArtifactStorage

**Puerto:** `src/storage/ports/artifact_storage.py`

- **Responsabilidad:** Escritura/lectura de artefactos bajo un directorio base (p. ej. `run_dir`).
- **Métodos:** `write_json`, `write_bytes`, `exists`, `list_artifacts`.

**Adaptador:** `FileSystemArtifactStorage` en `src/storage/adapters/`. El pipeline y la evidencia siguen escribiendo con la lógica actual; el puerto es preparatorio para una futura unificación.

---

## 5. Configuración y variables de entorno

La configuración se carga desde `.env` (ver `.env.example`) y se expone vía `src.config.Settings`. Variables relevantes para V2.3:

| Variable | Descripción | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Proveedor LLM: `gemini`, `openai`, `fake` | `gemini` |
| `FAKE_LLM_FIXTURE_PATH` | Ruta a JSON fixture para proveedor fake | — |
| `HYBRID_MAX_FRAMES` | Límite de frames en modo hybrid (vacío = cap interno 48) | — |
| `DEBUG_SAVE_FRAMES` | Guardar en `run/frames_sent/` los frames enviados al LLM | `false` |
| `OUTPUT_DIR` | Directorio base de salida (jobs y runs) | `output` |

El resto de variables (API, SQL Server, fotos, evidencia, etc.) se documentan en `.env.example` y en `src/config.py`.

---

## 6. Rutas de artefactos y reporte

- **Run directory:** `OUTPUT_DIR / job_id / run_id /` (p. ej. `output/job_abc/run/`).
- **Reporte híbrido:** `run_dir/hybrid_report.json` (schema v2.1, `report_version`, `mode`, `summary`, `entities`).
- **Evidencia:** `run_dir/evidence/` (por entidad) y `run_dir/evidence_index.json`.
- **Frames enviados (debug):** `run_dir/frames_sent/` cuando `DEBUG_SAVE_FRAMES=true`.

No se han cambiado rutas ni esquema del reporte en V2.3.

---

## 7. API y worker

- **API:** Los endpoints de jobs (`POST /api/v1/inventory/jobs`, `GET /{job_id}`, `GET /{job_id}/result`, etc.) no cambian en contrato ni comportamiento. Siguen usando `job_store` y `queue`.
- **Worker:** `run_job()` instancia `HybridInventoryPipeline()` sin argumentos (usa `GeminiAnalysisProvider` por defecto), llama a `process_video(...)` con `job_input` del job y actualiza estado/progreso/salida vía `job_store`. Compatible con V2.3.

---

## 8. Próximos pasos (fuera de V2.3)

- Conectar worker y/o API a `JobRepository` y `JobQueue` para desacoplar de la implementación actual.
- Usar `ArtifactStorage` en ReportingStage/EvidenceStage cuando se unifique la escritura de artefactos.
- Añadir pruebas de regresión de esquema de reporte y de rutas de evidencia si se prioriza garantizar compatibilidad a largo plazo.

---

## 9. Referencia de módulos

| Área | Ruta |
|------|------|
| Contexto | `src/pipeline/context/run_context.py` |
| Contrato de etapas | `src/pipeline/contracts/stage.py` |
| Etapas | `src/pipeline/stages/*.py` |
| Puerto de análisis | `src/pipeline/ports/analysis_provider.py` |
| Adaptador de análisis | `src/pipeline/adapters/gemini_analysis_provider.py` |
| Puertos de jobs | `src/jobs/ports/job_repository.py`, `job_queue.py` |
| Adaptadores de jobs | `src/jobs/adapters/*.py` |
| Almacenamiento | `src/storage/ports/artifact_storage.py`, `adapters/filesystem_artifact_storage.py` |
| Orquestador | `src/pipeline/hybrid_inventory_pipeline.py` |

---

*Documento generado para la versión 2.3 del sistema de inventario por visión. Actualizar al evolucionar la arquitectura.*
