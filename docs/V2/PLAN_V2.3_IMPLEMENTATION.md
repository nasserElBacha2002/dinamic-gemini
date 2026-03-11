# Plan de Implementación — Versión 2.3

## 1. Resumen Ejecutivo

### Objetivo global de la versión

La versión **2.3** tiene como objetivo **consolidar la arquitectura interna** del pipeline de inventario por visión computacional (video/fotos → frames → análisis global LLM → entidades → evidencia → reporte), sin añadir nuevas funcionalidades de negocio. Se busca:

- Separar responsabilidades (SRP), reducir acoplamiento (DIP) y preparar extensibilidad (OCP).
- Introducir una capa de aplicación clara (servicios de creación y ejecución de jobs).
- Formalizar el pipeline en etapas explícitas y un contexto de ejecución (`RunContext`).
- En una segunda fase, cerrar contratos (providers, frame sources, repositorios, storage) y DTOs tipados.
- En una tercera fase, introducir modelo de ejecución auditable (`Run`), persistencia estructurada y trazabilidad operativa.

### Justificación de por qué hacer 2.3 antes de 3.0

El sistema v2.2 ya cumple el flujo funcional (video/fotos, hybrid, evidence, reporte v2.1), pero la deuda estructural dificulta:

- **Extender** el flujo (nuevos inputs, nuevos providers, nuevas etapas).
- **Testear** en aislamiento (pipeline, worker y rutas mezclan lógica e infraestructura).
- **Operar** con confianza (estado repartido entre FS/DB, sin entidad Run, worker en el mismo proceso que la API).

Abordar 2.3 antes de 3.0 permite llegar a una v3.0 (escalado, observabilidad, multi-tenant, etc.) sobre una base mantenible y con fronteras claras entre dominio, aplicación e infraestructura.

### Alcance general

- **Incluido:** Refactor estructural del core (2.3.A), contratos e inversión de dependencias (2.3.B), ejecución fiable y auditoría (2.3.C). Sin cambio de comportamiento funcional observable para el usuario final.
- **Excluido:** Nuevas features de negocio, migración completa a cola distribuida, object storage remoto, observabilidad externa (Prometheus/tracing), reescritura total desde cero.

---

## 2. Diagnóstico del estado actual

### Principales debilidades detectadas

1. **`HybridInventoryPipeline` concentra demasiado**  
   En `src/pipeline/hybrid_inventory_pipeline.py`, `_run_hybrid` (~120 líneas) realiza en un solo método: normalización de fotos, resolución de FrameSource, obtención de frames, carga de imágenes a memoria, obtención del provider LLM, llamada al análisis, parseo, orden/resolución de entidades, asignación de count_status y quality_score, generación de evidence pack, construcción del reporte y escritura a disco. No hay etapas explícitas ni objeto de contexto compartido.

2. **Endpoints con lógica de aplicación e infraestructura**  
   En `src/api/routes/jobs.py`, `create_inventory_job` y los helpers `_create_job_video` / `_create_job_photos_form` realizan: validación de form, decisión de tipo de input, persistencia de archivos (streaming a disco), creación de directorios, llamada a `create_job` del job_store, encolado. El endpoint actúa como orquestador de creación en lugar de delegar en un servicio.

3. **Worker con caso de uso embebido**  
   En `src/jobs/worker.py`, `run_job` carga el job, valida modo legacy, carga settings, construye callback de progreso, instancia el pipeline, invoca `process_video`, interpreta el código de retorno, actualiza estado y output en job_store y llama a `_push_success_to_db` (que lee el JSON del reporte y empuja a DB). Toda la lógica del “caso de uso de ejecución” vive en el worker.

4. **Job store mezcla resolución de infraestructura y persistencia**  
   En `src/jobs/job_store.py`, `_db_repos()` resuelve si hay SQL Server y construye `(JobsRepository, PalletResultsRepository, JobEventsRepository)`. `create_job`, `get_job` y `update_job` orquestan FS + DB (escribir/leer job.json y, si hay DB, llamar a repos concretos). No existe un puerto `JobRepository`; el resto del sistema depende de las funciones del store.

5. **Estado del run disperso**  
   No hay un único objeto que agrupe `job_id`, `run_id`, `output_path`, `run_dir`, `settings`, `job_input`, `logger`, `progress_callback`, etc. Se pasan muchos parámetros sueltos entre pipeline y worker.

6. **Contratos parciales**  
   Existen `FrameSource` (protocol con `get_frames`) y `LLMProvider` (protocol con `analyze_global`), pero el pipeline sigue usando `get_frame_source(input_type)` y `get_llm_provider(settings)` directamente y conoce `JobInput`, `FramesBundle`, `LLMRequest`/`LLMResponse`. No hay DTOs explícitos de entrada/salida por etapa ni puertos para persistencia o cola.

7. **Cola y worker acoplados al proceso API**  
   En `src/api/server.py`, un thread en background ejecuta el mismo loop que consumiría un worker independiente (`dequeue` → `run_job`). No hay separación clara entre proceso API y proceso worker ni contrato de cola inyectable.

8. **Persistencia de resultado basada en JSON**  
   El worker y `_push_success_to_db` leen `hybrid_report.json` para rellenar `set_job_outputs` y `insert_pallet_results`. La fuente de verdad del resultado es el archivo; la DB es un derivado. No existe entidad `Run` ni registros de etapas o errores estructurados.

### Deuda técnica más importante

- **Ausencia de capa de aplicación:** No hay `CreateJobService` ni `ExecuteJobService`; la orquestación está en rutas y worker.
- **Pipeline monolítico:** Una sola función larga que hace todas las etapas; difícil de testear o sustituir una etapa.
- **Dependencia directa de infraestructura:** Pipeline y worker usan `load_settings()`, `Path`, `open`, repos concretos y `queue.Queue` sin abstracciones.
- **Sin modelo Run:** No se distingue entre “job” (intención) y “run” (ejecución concreta), lo que limita reintentos, auditoría y trazabilidad.

### Riesgos actuales de arquitectura

- **Regresión al extender:** Añadir un nuevo tipo de input o un nuevo provider implica tocar pipeline, rutas y/o worker en varios sitios.
- **Tests frágiles:** Tests de integración que dependen del flujo completo; pocos puntos para doblar solo una capa.
- **Operación:** Errores y estado repartidos entre logs, job.json, DB y archivos; difícil reconstruir “qué pasó en este run”.

---

## 3. Estrategia general de implementación

### Enfoque incremental

- **Extraer primero, mejorar después.** No reescribir de golpe: mover la lógica actual a componentes con responsabilidades claras manteniendo el comportamiento.
- **Por etapas 2.3.A → 2.3.B → 2.3.C.** Cada etapa tiene criterios de aceptación verificables y entrega valor arquitectónico sin romper el flujo funcional.
- **Preservar compatibilidad funcional:** Misma API HTTP, mismos reportes y artifacts; los cambios son internos.

### Orden recomendado

1. **2.3.A:** RunContext, etapas explícitas del pipeline, pipeline como orquestador, CreateJobService, ExecuteJobService, endpoints y worker finos.
2. **2.3.B:** Puertos (AnalysisProvider, FrameSource, JobRepository, JobQueue, ArtifactStorage, PromptBuilder), DTOs entre etapas, adaptación de Gemini y pipeline a contratos, tests de contrato.
3. **2.3.C:** Modelo Run, repositorios de runs/errores/artifacts/etapas, ExecuteJobService con ciclo de vida de run, logging estructurado, run_manifest.json, DB como fuente de verdad para estado y resultados.

### Principios técnicos rectores

- **SOLID:** Una responsabilidad por componente; extensión por nuevos tipos sin modificar el core; implementaciones sustituibles; interfaces pequeñas; dependencia en abstracciones.
- **Capas:** Dominio (entidades, reglas puras) → Aplicación (casos de uso, servicios) → Infraestructura (providers, repos, storage, cola) → Transporte (API) y Ejecución (worker).
- **Contratos explícitos:** Evitar `dict` ambiguos; DTOs o dataclasses tipados entre etapas y en puertos.
- **Refactor sin big-bang:** Cambios por fichero/módulo acotados; tests de humo antes y después de cada movimiento importante.

### Incremental Migration Strategy

Migration from the current system to the new architecture MUST be done in phases to avoid regressions and to allow rollback at any step.

**Phase 1 — Introduce interfaces without removing current implementations.**  
Define the new ports (e.g. JobRepository, JobQueue, AnalysisProvider) and DTOs. The existing code (job_store functions, queue module, GeminiProvider) remains unchanged and is still the one in use. No call site switches to the new interfaces yet. This phase only adds types and contracts.

**Phase 2 — Create adapters wrapping existing components.**  
Implement adapter classes that implement the new interfaces and delegate to the current implementations (e.g. JobStoreAdapter that implements JobRepository and calls create_job, get_job, update_job). The old APIs remain the source of truth; the adapters are a thin wrapper. Tests can start using the interfaces with these adapters.

**Phase 3 — Refactor pipeline and services to depend on the new interfaces.**  
Change the pipeline, ExecuteJobService, and CreateJobService to receive the new ports (injected via constructor or factory). Wire the composition root (bootstrap) to pass the adapters. The system now runs through interfaces, but the underlying implementation is still the original code. Run full regression and E2E tests after this step.

**Phase 4 — Remove or replace legacy components only when safe.**  
Once the new flow is stable and tests pass, legacy code paths that are no longer called can be removed or replaced (e.g. replace the adapter’s internal call to job_store with a direct DB implementation if desired). Each removal should be a separate, small change with tests confirming behavior.

This strategy prevents regressions by ensuring that at every phase the system remains functional and testable, and that no single change both introduces the abstraction and switches all call sites at once.

---

## 4. Etapa 2.3.A — Core Structural Refactor

### 4.1 Objetivo

Reorganizar la arquitectura interna para separar responsabilidades, introducir etapas explícitas del pipeline y un `RunContext`, y desacoplar API y worker del core de negocio, alineando con SRP, DIP y OCP. El comportamiento funcional (crear job, ejecutar con video/fotos, reporte v2.1) se mantiene.

### 4.2 Problemas actuales que resuelve

- **Pipeline con demasiadas responsabilidades:** `_run_hybrid` hace normalización, adquisición de frames, análisis, parseo, resolución de entidades, evidencia y reporte en un solo bloque. Se resuelve extrayendo etapas con interfaces claras.
- **Estado del run disperso:** Parámetros como `video_id`, `output_path`, `run_id`, `settings`, `job_input`, `logger`, `progress_callback` se pasan por kwargs. Se resuelve con un `RunContext` único.
- **Endpoint con lógica de creación:** La ruta POST crea directorios, persiste archivos, valida y encola. Se resuelve delegando en `CreateJobService`.
- **Worker con caso de uso embebido:** `run_job` orquesta carga de job, ejecución y persistencia de resultado. Se resuelve delegando en `ExecuteJobService`.
- **Sin etapas reutilizables:** No se puede testear o sustituir una fase (p. ej. solo “frame acquisition”) de forma aislada. Se resuelve con etapas que reciben contexto y datos tipados y devuelven resultados acotados.

### 4.3 Diseño propuesto

#### RunContext

Objeto inmutable o de solo escritura controlada que se crea al iniciar la ejecución y se pasa a todas las etapas.

**Contenido mínimo (2.3.A):**

- `job_id: str`
- `run_id: str`
- `workspace_path: Path` (ej. `output_dir / job_id`)
- `run_dir: Path` (ej. `workspace_path / run_id`)
- `job_input: JobInput` (ya existente en `src/jobs/models.py`)
- `settings: Settings`
- `logger: logging.Logger`
- `progress_callback: Optional[Callable[[str, int], None]]`
- `metadata: dict` (para extensión)
- Opcional: campos de **métricas de ejecución** (ej. timestamps de inicio/fin, contadores) para auditoría, nunca para pasar salidas entre etapas.

**Ubicación sugerida:** `src/pipeline/context/run_context.py`.

#### RunContext Usage Rules

RunContext MUST contain only:

- **Run metadata:** run_id, job_id, timestamps (created_at, etc.).
- **Job identifiers:** job_id y referencias al job (ej. job_input).
- **Configuration snapshot:** settings o effective_config usado en el run.
- **Logging context:** logger, y opcionalmente run_id/job_id para inyección en logs.
- **Artifact paths:** workspace_path, run_dir (rutas base donde se escriben artifacts).
- **Execution metrics:** contadores o timings de alto nivel para observabilidad (opcional).

RunContext **MUST NOT** be used as a shared mutable container for stage outputs. Stage outputs must travel through **explicit typed result objects** returned by each stage (PreparedInput, FrameBundleResult, RawAnalysisResult, etc.). This keeps each stage’s contract clear, avoids hidden coupling, and makes the pipeline testable (each stage can be tested with a given input DTO and expected output DTO).

**Correct pipeline usage example:**

```py
def _run_hybrid(self, context: RunContext) -> int:
    prepared = self.input_stage.run(context, None)           # or a minimal initial input
    frames = self.frame_stage.run(context, prepared)
    analysis = self.analysis_stage.run(context, frames)
    resolved = self.entity_stage.run(context, analysis)
    evidence = self.evidence_stage.run(context, resolved)
    report = self.reporting_stage.run(context, ReportStageInput(resolved=resolved, evidence=evidence))
    return 0 if report.success else 1
```

Data flows only via return values (prepared → frames → analysis → resolved → evidence → report). RunContext is read for paths, settings, logger, and progress callback only.

#### Etapas del pipeline

Cada etapa tiene una responsabilidad única y una firma homogénea. Se recomienda un protocolo:

```py
# src/pipeline/contracts/stage.py
class PipelineStage(Protocol[TIn, TOut]):
    def run(self, context: RunContext, data: TIn) -> TOut: ...
```

En 2.3.A los tipos pueden ser aún permisivos (`Any` o dataclasses mínimos) para no bloquear; en 2.3.B se endurecen a DTOs.

**Etapas a extraer desde la lógica actual de `_run_hybrid`:**

| Etapa | Responsabilidad | Input (conceptual) | Output (conceptual) |
|-------|-----------------|--------------------|----------------------|
| **InputPreparationStage** | Validar tipo de input, preparar rutas (run_dir, manifest/photos dirs). | RunContext | PreparedInput (job_id, input_type, paths relevantes) |
| **FrameAcquisitionStage** | Normalizar fotos si aplica; obtener FrameSource; get_frames; cargar imágenes a RAM (con límite). | RunContext, PreparedInput | FrameBundleResult (frames ndarray, frame_refs, metadata) |
| **AnalysisStage** | Obtener provider, construir LLMRequest, llamar analyze_global. | RunContext, FrameBundleResult | RawAnalysisResult (parsed_json, provider_name) |
| **EntityResolutionStage** | parse_entities, sort, resolve_pallet_id, assign_count_status, compute_entity_quality_score. | RunContext, RawAnalysisResult | ResolvedEntitiesResult (entities list) |
| **EvidenceStage** | generate_evidence_pack, escribir evidence/ y evidence_index.json. | RunContext, ResolvedEntitiesResult | EvidenceResult (paths o índice) |
| **ReportingStage** | build_hybrid_report, write_json hybrid_report.json (y CSV si aplica). | RunContext, ResolvedEntitiesResult (+ evidence/report paths) | ReportingResult (report_path, summary) |

**Orquestador:** `HybridInventoryPipeline` (o renombrado `HybridPipelineOrchestrator`) solo:

1. Recibe `RunContext` y opcionalmente parámetros de entrada ya resueltos.
2. Crea/secuencia las etapas (inyectadas o resueltas por factory).
3. Llama a cada etapa con el resultado de la anterior.
4. Devuelve código de salida y/o resultado final.

La implementación concreta de cada etapa puede vivir en `src/pipeline/stages/` (ej. `input_preparation_stage.py`, `frame_acquisition_stage.py`, etc.).

#### CreateJobService

- **Responsabilidades:** Validar comando de creación (input_type, archivos, límites), persistir uploads (delegando en el handler de fotos o en lógica de video ya existente), crear directorio del job, crear registro de job (vía abstracción de persistencia que por ahora puede ser la función `create_job` del job_store), encolar job_id.
- **No hace:** Ejecución del pipeline, reglas de dominio de entidades, generación de reportes.
- **Entrada:** Un DTO tipo `CreateJobCommand` (input_type, archivos o rutas, mode, confidence_threshold, metadata).
- **Salida:** Un DTO tipo `CreateJobResult` (job_id, status, mode, confidence_threshold) que la API devuelve como 202.

**Ubicación:** `src/application/services/create_job_service.py`. Los comandos/resultados pueden estar en `src/application/commands/` y `src/application/results/` (o en el mismo módulo del servicio en 2.3.A).

#### ExecuteJobService

- **Responsabilidades:** Cargar job por job_id (vía job_store o futuro JobRepository), validar que esté QUEUED, actualizar estado a RUNNING, construir RunContext, invocar el pipeline orquestador, según código de retorno actualizar estado (SUCCEEDED/FAILED) y output (paths del reporte/artifacts), y en caso de éxito llamar a la lógica que hoy está en `_push_success_to_db`.
- **No hace:** Consumir la cola (eso lo hace el worker); detalle de cómo se escriben los archivos (lo hace el pipeline/etapas).

**Ubicación:** `src/application/services/execute_job_service.py`.

#### Endpoint y worker

- **Endpoint POST /jobs:** Parsea el request (form), construye `CreateJobCommand`, llama `create_job_service.execute(command)`, mapea resultado a `JobCreateResponse`, devuelve 202. Toda la lógica de “cómo” crear directorios, guardar archivos y encolar queda dentro del servicio.
- **Worker:** Loop: obtener job_id de la cola (abstracción que por ahora puede ser `dequeue`); llamar `execute_job_service.execute(job_id)`; no contener lógica de negocio más allá de eso.

### 4.4 Historias de usuario

- **Como arquitecto del sistema,** quiero que el pipeline esté compuesto por etapas explícitas con una interfaz común, para poder testear y sustituir cada fase sin tocar el resto.  
  **Valor:** Mantenibilidad y testabilidad.  
  **Criterio de aceptación:** Existen al menos 6 clases de etapa (input preparation, frame acquisition, analysis, entity resolution, evidence, reporting), cada una con un método `run(context, input_data)` y el orquestador las invoca en secuencia.

- **Como arquitecto del sistema,** quiero un RunContext que agrupe job_id, run_id, paths, settings, logger y callback de progreso, para no pasar decenas de argumentos entre componentes.  
  **Valor:** Menor acoplamiento y código más legible.  
  **Criterio de aceptación:** RunContext se instancia al iniciar la ejecución y se pasa a todas las etapas; el pipeline y las etapas no reciben `video_id`, `output_path`, `run_id`, `settings`, `logger` por separado.

- **Como servicio de aplicación (CreateJobService),** quiero recibir un comando tipado (CreateJobCommand) y devolver un resultado tipado (CreateJobResult), para que la API solo traduzca HTTP ↔ comando/resultado.  
  **Valor:** Separación clara entre transporte y caso de uso.  
  **Criterio de aceptación:** El endpoint POST /jobs no contiene lógica de validación de negocio ni de persistencia de archivos; delega en CreateJobService; el servicio devuelve CreateJobResult con job_id y datos para la respuesta 202.

- **Como servicio de aplicación (ExecuteJobService),** quiero recibir un job_id y encargarme de cargar el job, crear RunContext, ejecutar el pipeline y actualizar estado y resultados, para que el worker solo consuma la cola y llame al servicio.  
  **Valor:** Caso de uso de ejecución en un solo lugar; worker reducido a adaptador.  
  **Criterio de aceptación:** El worker no contiene lógica de actualización de estado ni de lectura del reporte para DB; llama a ExecuteJobService.execute(job_id); el servicio orquesta pipeline y persistencia.

- **Como operador del sistema,** quiero que el comportamiento funcional (crear job con video o fotos, ejecutar, obtener hybrid_report.json y evidencia) no cambie tras el refactor, para no romper integraciones.  
  **Valor:** Refactor seguro.  
  **Criterio de aceptación:** Tests de humo o E2E existentes (video y fotos) siguen pasando; la API y los reportes mantienen el mismo formato.

### 4.5 Tareas técnicas

- **T1.** Crear `src/pipeline/context/run_context.py` con dataclass o clase `RunContext` (job_id, run_id, workspace_path, run_dir, job_input, settings, logger, progress_callback, metadata).
- **T2.** Crear `src/pipeline/contracts/stage.py` con protocolo `PipelineStage` (run(context, data) -> result). Opcional: tipos genéricos TIn, TOut.
- **T3.** Extraer **InputPreparationStage** desde el inicio de `_run_hybrid`: validar input_type, preparar run_dir y rutas; devolver objeto PreparedInput (puede ser un dataclass mínimo).
- **T4.** Extraer **FrameAcquisitionStage**: normalización de fotos (si input_type==photos), get_frame_source, get_frames, carga de imágenes con límite; devolver FrameBundleResult (frames, frame_refs, metadata).
- **T5.** Extraer **AnalysisStage**: get_llm_provider, construir LLMRequest, provider.analyze_global; devolver RawAnalysisResult (parsed_json, provider_name).
- **T6.** Extraer **EntityResolutionStage**: parse_entities, sort_entities_deterministically, resolve_pallet_id, assign_count_status, compute_entity_quality_score; devolver ResolvedEntitiesResult (entities).
- **T7.** Extraer **EvidenceStage**: generate_evidence_pack; devolver EvidenceResult (path del index o resumen).
- **T8.** Extraer **ReportingStage**: build_hybrid_report, write_json; devolver ReportingResult (report_path, summary).
- **T9.** Refactorizar `HybridInventoryPipeline`: en `_run_hybrid`, construir RunContext, instanciar las etapas (o recibirlas por constructor), ejecutarlas en orden pasando el output de una a la siguiente; devolver 0/1 según resultado. Eliminar la lógica inline movida a las etapas.
- **T10.** Crear `CreateJobCommand` y `CreateJobResult` (en application/commands y application/results o en el mismo módulo del servicio).
- **T11.** Implementar `CreateJobService.execute(command)`: validación, persistencia de archivos (reutilizar `persist_photos_from_uploads` y lógica de video actual), creación de directorios, llamada a `create_job` del job_store, `enqueue(job_id)`; devolver CreateJobResult.
- **T12.** Refactorizar `api/routes/jobs.py`: en create_inventory_job, construir CreateJobCommand desde el request.form(), llamar create_job_service.execute(command), mapear a JobCreateResponse y devolver 202.
- **T13.** Crear `ExecuteJobService.execute(job_id)`: get_job, comprobar QUEUED, update_job RUNNING, construir RunContext (run_dir, logger, progress_cb, etc.), instanciar pipeline y llamar process_video (o método que reciba RunContext), según retorno update_job SUCCEEDED/FAILED y output; en éxito llamar a la lógica actual de _push_success_to_db (moverla a un colaborador o al propio servicio).
- **T14.** Refactorizar `jobs/worker.py`: run_job(base_path, job_id) solo llama execute_job_service.execute(job_id). worker_loop sin cambios de interfaz (sigue dequeue → run_job). Ajustar run_job para obtener base_path de config si hace falta (o mantener parámetro para no tocar server).
- **T15.** Ajustar pipeline para que pueda recibir RunContext desde fuera (por ejemplo, ExecuteJobService construye el contexto y llama a un método `run(context)` del pipeline que internamente usa context.run_dir, context.settings, etc.).
- **T16.** Tests: añadir o ajustar tests de integración que ejecuten el flujo completo (crear job, ejecutar) y comprueben que el reporte y la evidencia se generan; opcionalmente tests unitarios de cada etapa con RunContext y datos de prueba.

### 4.6 Dependencias

- T1 (RunContext) es prerrequisito de T3–T9 y T13–T15.
- T2 (Stage protocol) es prerrequisito de T3–T8.
- T3–T8 pueden desarrollarse en paralelo una vez T1 y T2 existen; cada una solo depende del contrato de la etapa anterior (PreparedInput, FrameBundleResult, etc.).
- T9 depende de T3–T8.
- T10–T11 (CreateJobService) son independientes del pipeline; T12 depende de T11.
- T13 depende de T9 y T15 (pipeline que acepta RunContext).
- T14 depende de T13.
- T15 puede hacerse en paralelo a T9 (el orquestador debe usar RunContext en lugar de kwargs).
- T16 depende de T9, T12 y T14.

### 4.7 Riesgos

- **Regresión funcional:** Al extraer etapas, un error en el pasaje de datos (p. ej. frame_indices truncados) podría cambiar resultados. Mitigación: tests E2E antes del refactor; ejecutar los mismos casos después de cada extracción; comparar reportes en tests si es posible.
- **Orden de ejecución o dependencias entre etapas:** Si una etapa espera un campo que otra no rellena, fallos en runtime. Mitigación: definir explícitamente los DTOs mínimos de salida de cada etapa y usarlos en la siguiente; tests unitarios por etapa con mocks de la anterior.
- **Deadlock o cambios en el worker:** Si ExecuteJobService tarda más o hace I/O distinta, el worker thread podría comportarse distinto. Mitigación: mantener la misma forma de invocar run_job (por job_id); no cambiar la semántica de la cola en 2.3.A.

### 4.8 Criterios de aceptación

- Existe `RunContext` con los campos descritos y se usa en todas las etapas y en el orquestador.
- Existen las 6 etapas (InputPreparation, FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting) con método `run(context, input_data)` y el orquestador las invoca en secuencia sin duplicar la lógica que hoy está en `_run_hybrid`.
- Existe `CreateJobService` que recibe un comando tipado y realiza validación, persistencia y encolado; el endpoint POST /jobs solo construye el comando y devuelve el resultado del servicio.
- Existe `ExecuteJobService` que recibe job_id, carga el job, actualiza estado, ejecuta el pipeline (con RunContext) y actualiza resultado/DB; el worker solo llama a este servicio.
- Los tests de integración/E2E existentes (video y fotos) pasan; no se introduce cambio observable en la API ni en el formato del reporte.

---

## 5. Etapa 2.3.B — Contracts, Interfaces & Dependency Inversion

### 5.1 Objetivo

Formalizar los contratos del sistema (puertos para provider, frame source, repositorio, cola, storage, prompt builder), introducir DTOs tipados entre etapas y desacoplar el core de implementaciones concretas (Gemini, filesystem, queue, SQL Server), alineando con OCP, LSP, ISP y DIP.

### 5.2 Problemas actuales que resuelve

- **Pipeline y worker dependen de implementaciones concretas:** Uso directo de `get_llm_provider(settings)`, `get_frame_source(input_type)`, `create_job`/`get_job`/`update_job` del job_store, `enqueue`/`dequeue` de la cola y escritura directa a `Path`. Se resuelve inyectando puertos y usando DTOs en las etapas.
- **Contratos parciales:** `LLMProvider` y `FrameSource` existen pero el pipeline sigue resolviendo implementaciones por nombre; no hay contrato para persistencia ni cola. Se resuelve definiendo puertos y haciendo que los servicios y el pipeline dependan de ellos.
- **Datos entre etapas como dict o tipos internos:** Se pasan `metadata`, `bundle.metadata`, `response.parsed_json`, etc. Se resuelve con DTOs (PreparedInput, FrameBundleResult, RawAnalysisResult, ResolvedEntitiesResult, EvidenceResult, ReportingResult) con campos bien definidos.
- **Gemini y prompt acoplados al flujo:** El pipeline usa `GLOBAL_ENTITY_ANALYSIS_PROMPT_V21` y el provider devuelve estructuras que el pipeline interpreta. Se resuelve con un contrato AnalysisProvider (request/response) y opcionalmente PromptBuilder, de forma que el pipeline no dependa del SDK de Gemini.

### 5.3 Diseño propuesto

#### Puertos (interfaces)

- **AnalysisProvider (Protocol):** `analyze(request: AnalysisRequest) -> AnalysisResponse`. Request: run_id, prompt, schema_version, imágenes (paths o bytes), metadata. Response: provider_name, model_name, raw_text, parsed_payload (dict v2.1), usage, latency_ms, warnings. Ubicación: `src/application/ports/analysis_provider.py` (o `src/pipeline/contracts/` si se prefiere que los puertos del pipeline vivan ahí).
- **FrameSource (ya existe como protocolo):** En 2.3.B se puede endurecer el contrato: entrada tipada (FrameCollectionRequest: input_type, video_path, photo_paths, max_frames, etc.) y salida tipada (FrameCollectionResult: frames, frame_refs, metadata). Las implementaciones actuales (VideoFrameSource, PhotosFrameSource) se adaptan para cumplir ese contrato.
- **JobRepository (Protocol):** create(job_record), get(job_id) -> JobRecord | None, update(job_id, updates). El job_store actual se puede envolver en un adaptador que implemente este protocolo y que internamente llame a create_job, get_job, update_job.
- **JobQueue (Protocol):** enqueue(job_id), dequeue(timeout) -> job_id | None. La cola actual en `src/jobs/queue.py` se envuelve en una clase InMemoryJobQueue que implemente el protocolo.
- **ArtifactStorage (Protocol):** write_json(relative_path, payload) -> path escrito; write_bytes(relative_path, content, content_type); exists(relative_path). Primera implementación: FileSystemArtifactStorage que escribe bajo run_dir.
- **PromptBuilder (Protocol):** build(context: RunContext, frame_bundle: FrameBundleResult) -> PromptPayload (system_prompt, user_prompt, schema_version). Permite extraer la construcción del prompt del pipeline y del provider.

#### DTOs

- Definir en `src/application/dto/` o `src/pipeline/dto/`: PreparedInput, FrameBundleResult (o reutilizar/alinear con FramesBundle existente), RawAnalysisResult, ResolvedEntitiesResult, EvidenceResult, ReportingResult, y para el provider: AnalysisRequest, AnalysisResponse, AnalysisImage.
- Las etapas pasan a recibir y devolver estos tipos en lugar de dict o tipos internos del LLM.

#### Pipeline y servicios

- El orquestador y las etapas reciben por constructor (o por factory) los puertos que necesitan: AnalysisProvider, FrameSource (o factory), JobRepository, ArtifactStorage, PromptBuilder. ExecuteJobService recibe JobRepository, Pipeline (orquestador), y opcionalmente JobQueue para futura extensión; CreateJobService recibe JobRepository y JobQueue.
- En el bootstrap (app o un módulo de composición), se instancian las implementaciones concretas (GeminiProvider, FileSystemArtifactStorage, adaptador del job_store, InMemoryJobQueue) y se inyectan en los servicios y en el pipeline.

#### Interface Creation Policy

Interfaces (Protocols / ports) MUST only be introduced when at least one of the following conditions holds:

1. **There is more than one implementation.** For example: AnalysisProvider (Gemini, Fake, future OpenAI); JobQueue (InMemory, future Database).
2. **Tests require mocking.** The component is a dependency that must be replaced by a double in unit or integration tests (e.g. JobRepository, ArtifactStorage).
3. **The component represents a known variability point.** The team has agreed that this dependency will be swapped or extended (e.g. FrameSource for video vs photos; storage for FS vs future object storage).

If none of these conditions apply, prefer using the concrete implementation until a second implementation or a test need appears. Unnecessary abstraction leads to over-engineering, extra indirection, and maintenance cost without benefit. When in doubt, defer introducing the interface until the second use case or the first test that needs a double.

### 5.4 Historias de usuario

- **Como pipeline (orquestador),** quiero depender de un contrato AnalysisProvider y no de Gemini ni de get_llm_provider(settings), para poder sustituir el proveedor sin tocar el core.  
  **Valor:** OCP y DIP.  
  **Criterio de aceptación:** El análisis global se invoca mediante una interfaz AnalysisProvider; la implementación concreta (Gemini) se inyecta desde el compositor; existen tests de contrato que verifican que una implementación fake cumple el contrato.

- **Como etapa de análisis,** quiero recibir y devolver DTOs (AnalysisRequest, AnalysisResponse o RawAnalysisResult), para que el contrato entre etapas sea estable y comprobable.  
  **Valor:** Contratos explícitos y menos errores de integración.  
  **Criterio de aceptación:** AnalysisStage recibe un DTO de frames/prompt y devuelve RawAnalysisResult; no se pasan dict sin tipo ni respuestas crudas del SDK.

- **Como servicio de aplicación,** quiero depender de JobRepository y JobQueue en lugar de job_store y queue directamente, para poder sustituir persistencia y cola en tests y en futuras implementaciones.  
  **Valor:** Testabilidad y preparación para cola persistente.  
  **Criterio de aceptación:** CreateJobService y ExecuteJobService reciben JobRepository (y CreateJobService también JobQueue); el compositor inyecta adaptadores del job_store y de la cola actual.

- **Como módulo de infraestructura (Gemini),** quiero implementar el puerto AnalysisProvider de forma que el pipeline no conozca detalles del SDK, para mantener el core estable ante cambios del proveedor.  
  **Valor:** LSP y mantenibilidad.  
  **Criterio de aceptación:** Existe una clase GeminiAnalysisProvider que implementa el protocolo AnalysisProvider; el pipeline solo usa request/response del contrato.

### 5.5 Tareas técnicas

- **T1.** Definir en `src/application/ports/` (o pipeline/contracts): AnalysisProvider, AnalysisRequest, AnalysisResponse (y AnalysisImage si aplica).
- **T2.** Definir JobRepository (create, get, update) y adaptar job_store para exponer un adaptador que lo implemente.
- **T3.** Definir JobQueue (enqueue, dequeue) e implementar InMemoryJobQueue en `src/infrastructure/queue/` (o jobs/adapters).
- **T4.** Definir ArtifactStorage (write_json, write_bytes, exists) e implementar FileSystemArtifactStorage.
- **T5.** Definir FrameSource con request/result tipados (FrameCollectionRequest, FrameCollectionResult / reutilizar FramesBundle) y adaptar VideoFrameSource y PhotosFrameSource para cumplir el contrato.
- **T6.** Definir PromptBuilder y PromptPayload; extraer la construcción del prompt actual a InventoryPromptBuilder (o similar) que use GLOBAL_ENTITY_ANALYSIS_PROMPT_V21.
- **T7.** Crear GeminiAnalysisProvider que implemente AnalysisProvider, envolviendo la lógica actual de GeminiProvider y GeminiGlobalAnalyzer; recibir AnalysisRequest y devolver AnalysisResponse.
- **T8.** Refactorizar AnalysisStage para usar AnalysisProvider inyectado y DTOs; recibir FrameBundleResult y devolver RawAnalysisResult.
- **T9.** Refactorizar el orquestador y el resto de etapas para usar DTOs en entradas/salidas (PreparedInput, FrameBundleResult, RawAnalysisResult, ResolvedEntitiesResult, EvidenceResult, ReportingResult).
- **T10.** Refactorizar ExecuteJobService y CreateJobService para recibir JobRepository (y CreateJobService JobQueue) por constructor; compositor en server o en un módulo de bootstrap que instancie repos y cola e inyecte en servicios.
- **T11.** EvidenceStage y ReportingStage usar ArtifactStorage para escribir JSON (o al menos definir el puerto y usar una implementación que escriba en run_dir).
- **T12.** Tests de contrato: test que una implementación fake de AnalysisProvider cumple la interfaz; test que FrameSource video y photos devuelven la estructura esperada; test de servicios con dobles de JobRepository y JobQueue.

### 5.6 Dependencias

- T1 es base para T7 y T8.
- T2 y T3 son independientes; T10 depende de ambos.
- T4 es base para T11.
- T5 es base para T9 (etapas que usen FrameSource con contrato).
- T6 es opcional para 2.3.B pero recomendable; T8 puede usar prompt estático mientras tanto.
- T7 depende de T1; T8 depende de T1 y T7.
- T9 depende de T5 y de los DTOs; T11 depende de T4.
- T12 depende de T1–T11.

### 5.7 Riesgos

- **Sobrediseño:** Introducir demasiados puertos o DTOs que no se usen. Mitigación: definir solo los puertos que tienen al menos dos “lados” (consumidor y proveedor) o una necesidad clara de sustitución en tests.
- **Incompatibilidad de LSP:** Que GeminiAnalysisProvider no cumpla realmente el contrato (p. ej. campos opcionales que el pipeline asume presentes). Mitigación: tests de contrato con request/response de ejemplo; documentar precondiciones y postcondiciones del protocolo.
- **Fugas de implementación:** Que el pipeline siga accediendo a detalles de Gemini (p. ej. excepciones propias del SDK). Mitigación: mapear excepciones del provider a un tipo de error de dominio o del contrato en el adaptador.

### 5.8 Criterios de aceptación

- Existen los puertos AnalysisProvider, JobRepository, JobQueue, ArtifactStorage y (opcional) PromptBuilder y FrameSource con request/result tipados; el pipeline y los servicios de aplicación dependen de estos puertos, no de implementaciones concretas.
- Las etapas intercambian DTOs tipados (PreparedInput, FrameBundleResult, RawAnalysisResult, ResolvedEntitiesResult, EvidenceResult, ReportingResult); no se pasan dict ambiguos entre etapas.
- Gemini se usa a través de una implementación de AnalysisProvider; el pipeline no importa el módulo Gemini directamente.
- Hay al menos un test de contrato para AnalysisProvider y, si aplica, para FrameSource; los servicios pueden testearse con dobles de JobRepository y JobQueue.

---

## 6. Etapa 2.3.C — Execution Reliability, Persistence & Auditability

### 6.1 Objetivo

Consolidar la arquitectura para operación confiable: introducir un modelo formal de ejecución (`Run`), persistencia estructurada de runs, errores, artifacts y etapas, logging estructurado con job_id/run_id/stage, y separación clara entre API y worker, con DB como fuente de verdad para estado y resultados estructurados (no el JSON del reporte como única fuente).

### 6.2 Problemas actuales que resuelve

- **Sin entidad Run:** No existe un concepto de “ejecución concreta” con identidad propia; solo job y archivos. Se resuelve con RunRecord (run_id, job_id, status, timestamps, provider, config snapshot, etc.) y repositorios de runs.
- **Resultado persistido vía JSON:** El worker y _push_success_to_db leen hybrid_report.json para rellenar DB; la fuente de verdad del resultado es el archivo. Se resuelve persistiendo entidades y resumen del run en DB desde los objetos que produce el pipeline; el JSON queda como artifact exportable.
- **Errores y estado dispersos:** No hay registro estructurado de errores por run ni de qué etapa falló. Se resuelve con RunErrorRecord y persistencia en run_errors (o equivalente).
- **Logging sin estándar:** Los logs no llevan de forma consistente job_id, run_id, stage. Se resuelve con un logger estructurado o convención de campos extra en cada log relevante.
- **Worker en el mismo proceso que la API:** El thread del worker en server.py comparte proceso con uvicorn. Se resuelve conceptualmente (entrypoint separado para worker) y documentando que API y worker son componentes distintos; opcionalmente ejecutar worker como proceso separado.

### 6.3 Diseño propuesto

- **RunRecord:** run_id, job_id, status (PENDING, RUNNING, SUCCEEDED, FAILED, PARTIAL, CANCELED), engine_version, schema_version, provider_name, provider_model, started_at, finished_at, duration_ms, effective_config_snapshot, warning_count, error_code, error_message. Tabla `runs` (o equivalente) y RunRepository (create_for_job, get, mark_running, mark_succeeded, mark_failed).
- **RunStageExecutionRecord:** run_id, stage_name, status, started_at, finished_at, duration_ms, input_summary, output_summary, warning_count, error_message. Persistir al menos un resumen por etapa (o por las etapas críticas) para trazabilidad.
- **RunErrorRecord:** run_id, stage_name, error_code, error_type, message, details, retriable, occurred_at. Tabla run_errors y RunErrorRepository.
- **RunArtifactRecord:** run_id, artifact_type, artifact_ref, content_type, metadata. Para referenciar reporte JSON, evidence_index, CSV, etc., sin depender del filesystem como única fuente de verdad.
- **DB como fuente de verdad:** Para estado del job y del run, resultados estructurados (entidades, resumen de conteo) y errores. Los archivos (hybrid_report.json, evidence packs) se consideran artifacts referenciados desde la DB; el contenido pesado sigue en artifact storage (filesystem en 2.3.C).
- **ExecuteJobService (refactorizado):** Crear Run al iniciar, marcar RUNNING, ejecutar pipeline, persistir resultados desde los DTOs (ResolvedEntitiesResult, ReportingResult) en runs y tablas relacionadas; en éxito marcar run SUCCEEDED y job SUCCEEDED; en fallo persistir RunErrorRecord y marcar run y job FAILED. Opcionalmente persistir StageExecutionRecord por etapa.
- **run_manifest.json:** Artifact que describe el run (run_id, job_id, engine_version, provider, input summary, frames count, stages, warnings, artifact refs, result_summary). Se escribe en run_dir y opcionalmente se referencia en RunArtifactRecord.
- **Logging estructurado:** Convención de campos (job_id, run_id, stage, event, duration_ms, etc.) en logs; puede ser un wrapper de logger que inyecte context o un módulo shared que defina la estructura.
- **Separación API / worker:** Mismo código de worker pero documentado como componente independiente; opcionalmente un entrypoint `python -m src.worker` que solo ejecute el loop de cola; el servidor API no arranque el worker en 2.3.C si se desea ejecución separada (o se mantiene el thread pero con la intención clara de que en producción se pueda desacoplar).

#### Operational Consistency Rules

The following invariants MUST hold for reliable operation and auditability:

- **A Run cannot finish as SUCCEEDED without persisted structured results.** If the pipeline completes successfully, the run’s result (entities, summary, artifact refs) MUST be written to the DB (or to the agreed source of truth) before the run is marked SUCCEEDED. This avoids “success” runs with no queryable outcome.

- **Artifact export failures must produce PARTIAL or FAILED runs.** If writing hybrid_report.json or evidence_index.json fails after the pipeline has produced in-memory results, the run MUST NOT be marked SUCCEEDED without at least persisting the structured result and marking the run as PARTIAL (or FAILED if the failure is critical). This keeps state consistent with what actually exists on disk or in storage.

- **When DB is enabled, system state must be derived exclusively from DB.** Queries for job status, run status, and results MUST read from the database (jobs, runs, run_entities, etc.), not from files. Artifact paths in DB point to where files are stored; the files are derived outputs. This eliminates ambiguity about source of truth.

- **Artifacts are derived outputs, not the source of truth.** hybrid_report.json, evidence_index.json, and run_manifest.json are exports for consumption by clients or operators. The application MUST NOT rely on parsing these files as the primary way to know run outcome or entity counts; that data MUST be persisted structurally (tables, RunRecord, RunEntityRecord, etc.) and artifacts generated from that or from the same DTOs.

- **All execution errors must produce a RunErrorRecord.** Any unhandled exception or handled failure in the pipeline or ExecuteJobService that causes the run to fail MUST result in a RunErrorRecord (or equivalent) being persisted with run_id, stage_name, error_code, and message. This ensures every failure is auditable and debuggable.

These invariants are necessary so that operators can trust job/run status, reproduce and audit outcomes, and diagnose failures without relying on ad-hoc logs or missing state.

### 6.4 Historias de usuario

- **Como operador del sistema,** quiero que cada ejecución tenga un Run persistido con estado, timestamps y resumen, para poder auditar y depurar sin depender solo de archivos.  
  **Valor:** Auditoría y operación.  
  **Criterio de aceptación:** Tras cada ejecución existe un registro Run con run_id, job_id, status, started_at, finished_at y al menos un resumen de resultado; se persiste en DB cuando está habilitada.

- **Como operador del sistema,** quiero que los errores de ejecución queden guardados con código, etapa y mensaje, para poder analizar fallos sin buscar en logs no estructurados.  
  **Valor:** Depuración y soporte.  
  **Criterio de aceptación:** Cualquier fallo en el pipeline o en el servicio persiste un RunErrorRecord (o equivalente) con run_id, stage_name, error_code, message; consultable vía repositorio o API.

- **Como servicio de aplicación (ExecuteJobService),** quiero persistir el resultado del run (entidades, resumen) directamente desde los DTOs del pipeline, para no depender del JSON del reporte como fuente principal.  
  **Valor:** Consistencia y fuente de verdad en DB.  
  **Criterio de aceptación:** Los datos que hoy se extraen de hybrid_report.json para set_job_outputs e insert_pallet_results se obtienen de ResolvedEntitiesResult y ReportingResult y se persisten en runs/run_entities (o tablas equivalentes); el reporte JSON se sigue generando como artifact.

- **Como operador del sistema,** quiero logs que incluyan job_id, run_id y stage de forma consistente, para poder filtrar y correlacionar en un agregador de logs.  
  **Valor:** Observabilidad.  
  **Criterio de aceptación:** Los logs emitidos durante la ejecución del pipeline y del servicio incluyen al menos job_id, run_id y stage (o event) en campos estructurados (extra o atributos).

### 6.5 Tareas técnicas

- **T1.** Modelo RunRecord y tabla `runs` (o ampliar schema existente); RunRepository (create_for_job, get, mark_running, mark_succeeded, mark_failed).
- **T2.** Modelo RunErrorRecord y tabla run_errors; RunErrorRepository (save).
- **T3.** Modelo RunStageExecutionRecord (opcional) y tabla run_stage_executions; RunStageRepository (save).
- **T4.** Modelo RunArtifactRecord y tabla run_artifacts; RunArtifactRepository (save, list_by_run).
- **T5.** Refactorizar ExecuteJobService: al iniciar, crear Run y marcarlo RUNNING; al finalizar con éxito, persistir resultado desde DTOs (entidades, summary) en runs y tablas relacionadas, marcar run SUCCEEDED y job SUCCEEDED; en excepción, persistir RunErrorRecord, marcar run y job FAILED.
- **T6.** Generar y escribir run_manifest.json en run_dir con run_id, job_id, provider, input summary, frames, stages, warnings, artifact refs, result_summary; opcionalmente registrar el artifact en RunArtifactRepository.
- **T7.** Instrumentar etapas (o el orquestador) para registrar StageExecutionRecord (started_at, finished_at, duration_ms, resumen de input/output) y persistir vía RunStageRepository.
- **T8.** Introducir logging estructurado: módulo o helper que reciba job_id, run_id, stage y emita logs con esos campos en `extra`; usar en pipeline y ExecuteJobService.
- **T9.** Migración de datos/schema: scripts o migraciones SQL para tablas runs, run_errors, run_stage_executions, run_artifacts (y run_entities si se persisten entidades por run).
- **T10.** Documentar y, si se desea, implementar entrypoint separado para worker (ej. `python -m src.worker`) que no arranque la API; el servidor puede seguir arrancando el worker en thread por defecto pero con la opción de desactivarlo para despliegue separado.

### 6.6 Dependencias

- T1 es base de T5.
- T2 es base de T5 (persistir errores).
- T3 y T4 son base de T5 y T6/T7.
- T5 depende de T1–T4 y del refactor de 2.3.B (DTOs y servicios).
- T6 y T7 dependen de T4 y T5.
- T8 es independiente; T9 es previo a desplegar con nuevas tablas.
- T10 es independiente del resto.

### 6.7 Riesgos

- **Duplicación temporal de persistencia:** Durante la transición, puede persistirse tanto en JSON como en runs/entidades; hay que dejar claro en el diseño que la fuente de verdad para consultas y estado es la DB.
- **Rendimiento:** Escribir en varias tablas (runs, run_errors, run_artifacts, run_entities) por cada ejecución puede añadir latencia. Mitigación: inserciones batch si hay muchas entidades; transacciones acotadas.
- **Compatibilidad con despliegues actuales:** Si hoy no se usa DB, las nuevas tablas y el RunRepository deben ser opcionales o tener modo “solo FS” para no romper entornos sin SQL Server. Mitigación: comprobar sqlserver_enabled antes de escribir en runs; si no hay DB, Run puede quedar en memoria o solo en run_manifest.json.

### 6.8 Criterios de aceptación

- Existe el modelo Run y se persiste un Run por cada ejecución (run_id, job_id, status, timestamps, provider, resumen); cuando DB está habilitada, los datos viven en tabla(s) de runs.
- Los errores de ejecución se persisten en run_errors (o equivalente) con run_id, stage, error_code, message.
- El resultado del run (entidades, resumen) se persiste en DB desde los DTOs del pipeline; el reporte JSON es un artifact más, no la única fuente de verdad para la aplicación.
- Los logs relevantes incluyen job_id, run_id y stage (o event) de forma estructurada.
- Existe run_manifest.json (o equivalente) que describe el run y sus artifacts; opcionalmente se registra en run_artifacts.
- API y worker están documentados como componentes separables; opcionalmente el worker puede ejecutarse como proceso independiente.

---

## 7. Orden de implementación recomendado

1. **2.3.A (en orden sugerido)**  
   - RunContext y contrato de etapa (T1, T2).  
   - Extraer etapas una a una (T3 → T4 → T5 → T6 → T7 → T8), manteniendo el pipeline funcionando después de cada extracción.  
   - Orquestador que use RunContext y etapas (T9, T15).  
   - CreateJobService y adaptación del endpoint (T10, T11, T12).  
   - ExecuteJobService y adaptación del worker (T13, T14).  
   - Tests de integración (T16).

2. **2.3.B**  
   - Definir puertos y DTOs (T1–T6).  
   - Implementar adaptadores (job_store → JobRepository, queue → JobQueue, FileSystemArtifactStorage, GeminiAnalysisProvider) (T2–T4, T7).  
   - Refactorizar etapas y orquestador para usar puertos y DTOs (T8, T9, T11).  
   - Inyección en servicios y compositor (T10).  
   - Tests de contrato (T12).

3. **2.3.C**  
   - Modelos y repositorios de Run, RunError, RunStage, RunArtifact (T1–T4, T9).  
   - Refactor de ExecuteJobService con ciclo de vida de Run (T5).  
   - run_manifest.json e instrumentación de etapas (T6, T7).  
   - Logging estructurado (T8).  
   - Entrypoint/documentación worker (T10).

---

## 8. Testing Requirements

Testing expectations MUST be met per stage to ensure the refactor does not introduce regressions and that contracts are enforceable.

### Stage 2.3.A

- **Stage unit tests:** Each pipeline stage (InputPreparation, FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting) MUST have at least one unit test that invokes `stage.run(context, input_data)` with a minimal RunContext and a representative or mock input, and asserts on the type and key fields of the returned result. This validates that stages have a clear input/output contract and that extraction from the monolith did not change behavior.
- **End-to-end smoke test:** At least one E2E test MUST run the full flow: create job (video or photos), execute job (via ExecuteJobService or worker), and assert that hybrid_report.json and evidence (e.g. evidence_index.json) exist and that the report structure is unchanged (e.g. entities, report_version). This guards against functional regressions.

### Stage 2.3.B

- **Contract tests for providers:** There MUST be tests that verify any implementation of AnalysisProvider (e.g. FakeProvider, GeminiAnalysisProvider) accepts an AnalysisRequest and returns an AnalysisResponse that satisfies the contract (required fields present, types correct). Same idea for FrameSource if the contract is formalized: given a FrameCollectionRequest, the result must be a FrameCollectionResult with the expected shape. Contract tests are critical so that new or alternative implementations cannot silently break the pipeline by returning a different shape.
- **Contract tests for repositories:** JobRepository and JobQueue MUST have contract tests: e.g. create then get returns the same job; enqueue then dequeue returns the same job_id. This ensures adapters and future implementations (e.g. DatabaseJobQueue) behave consistently.
- **Contract tests for queue:** JobQueue MUST be tested for enqueue/dequeue semantics (ordering, timeout behavior) so that InMemoryJobQueue and any future implementation are interchangeable from the consumer’s perspective.

### Stage 2.3.C

- **Run lifecycle tests:** Tests MUST cover: run is created and marked RUNNING when execution starts; run is marked SUCCEEDED when the pipeline completes and structured result is persisted; run is marked FAILED when an error occurs and RunErrorRecord is persisted. This validates that the operational consistency rules (e.g. no SUCCEEDED without persisted results) are enforced.
- **Persistence tests:** When DB is enabled (or mocked), tests MUST verify that run result data (e.g. entity count, report path) is persisted in runs/run_entities (or equivalent) and that the same data is not only present in JSON artifacts. This ensures DB is the source of truth.
- **Failure handling tests:** Tests MUST cover at least one failure path (e.g. pipeline raises, provider raises) and assert that a RunErrorRecord is created and the run and job are marked FAILED. This ensures the invariant “all execution errors produce a RunErrorRecord” is met.

Contract tests are critical because they encode the expected behavior of a port; any implementation (production or test double) must pass them, which prevents drift and supports safe substitution (LSP) and testability.

---

## 9. Quick wins

- **RunContext (2.3.A):** Introducir solo el RunContext y usarlo dentro del pipeline actual sin extraer etapas todavía; reduce parámetros y prepara el terreno. Bajo costo, alto impacto en claridad.
- **JobQueue como interfaz (2.3.B temprano):** Definir el protocolo JobQueue y envolver la cola actual en InMemoryJobQueue; el worker y CreateJobService dependen del puerto. Permite testear con doble y prepara cola persistente.
- **DTOs de salida de AnalysisStage (2.3.B):** Definir RawAnalysisResult (parsed_json, provider_name) y que AnalysisStage lo devuelva; EntityResolutionStage lo recibe tipado. Reduce acoplamiento con el SDK sin tocar aún el resto de etapas.
- **run_manifest.json (2.3.C):** Escribir un manifest mínimo (run_id, job_id, provider, frame_count, report_path) al finalizar el run, sin necesidad de todas las tablas de runs. Mejora trazabilidad con poco esfuerzo.
- **Logging con job_id/run_id (2.3.C):** Añadir un helper que inyecte job_id y run_id en logger.info(..., extra={...}) en el worker y en el pipeline. Mejora operación sin cambiar modelo de datos.

---

## 10. Riesgos globales

- **Alcance de 2.3:** Las tres etapas juntas son un refactor grande. Riesgo de fatiga y de dejar a medias. Mitigación: cerrar 2.3.A con criterios de aceptación estrictos antes de pasar a 2.3.B; lo mismo entre B y C. No mezclar objetivos de distintas etapas en el mismo PR grande.
- **Compatibilidad con E2E y clientes:** Cualquier cambio en rutas o formato de respuesta puede romper integraciones. Mitigación: no cambiar la API HTTP en 2.3; mantener el mismo contrato de POST /jobs y de reportes; tests E2E en CI.
- **SQL Server y despliegues sin DB:** Si 2.3.C introduce tablas runs y se asume DB, entornos que hoy solo usan FS pueden quedar sin soporte. Mitigación: hacer que Run y errores sean opcionales cuando sqlserver_enabled es false; run_manifest.json y logs estructurados sí pueden existir siempre.
- **Regresión de rendimiento:** Más capas y más escrituras (runs, stages, errors) pueden añadir latencia. Mitigación: medir un flujo típico antes y después; mantener inserciones mínimas necesarias en 2.3.C.

---

## 11. Definition of Done de la versión 2.3

La versión 2.3 se considerará cerrada cuando se cumpla lo siguiente:

**2.3.A**  
- RunContext existe y se usa en el pipeline y en ExecuteJobService.  
- Las 6 etapas existen y el orquestador las invoca en secuencia.  
- CreateJobService y ExecuteJobService existen; el endpoint y el worker delegan en ellos.  
- Tests de integración/E2E (video y fotos) pasan; no hay cambio funcional observable.

**2.3.B**  
- Puertos AnalysisProvider, JobRepository, JobQueue, ArtifactStorage (y opcionalmente PromptBuilder/FrameSource tipados) están definidos y el pipeline/servicios dependen de ellos.  
- Las etapas intercambian DTOs tipados; Gemini se usa vía implementación de AnalysisProvider.  
- Al menos un test de contrato para AnalysisProvider (y opcionalmente FrameSource); servicios testeables con dobles.

**2.3.C**  
- Existe modelo Run y se persiste un Run por ejecución cuando DB está habilitada.  
- Errores de ejecución se persisten de forma estructurada (run_errors o equivalente).  
- El resultado del run se persiste en DB desde DTOs; el reporte JSON es artifact.  
- Logs relevantes incluyen job_id, run_id y stage de forma estructurada.  
- run_manifest.json se genera y opcionalmente se registra; API y worker documentados como componentes separables.

**Global (obligatorio para cerrar 2.3)**  
- **Pipeline no longer depends on concrete implementations.** The pipeline and its stages MUST depend only on ports (AnalysisProvider, FrameSource, ArtifactStorage, etc.) or on DTOs; they MUST NOT import or instantiate Gemini, job_store, queue, or filesystem directly.  
- **Worker contains no business logic.** The worker MUST only: obtain job_id from the queue, call ExecuteJobService.execute(job_id), and handle process-level concerns (e.g. loop, shutdown). It MUST NOT contain logic for loading job, building RunContext, updating job status, or pushing results to DB; that belongs in ExecuteJobService.  
- **Each execution generates a Run.** Every invocation of the pipeline (via ExecuteJobService) MUST create and persist a Run record (when DB is enabled) or at least produce a run_manifest.json / in-memory Run when DB is disabled, so that every execution is identifiable and auditable.  
- **Results are persisted structurally.** The outcome of a run (entities, summary, artifact refs) MUST be written to the database (or agreed source of truth) from DTOs produced by the pipeline, not by re-parsing JSON files.  
- **JSON artifacts are derived outputs.** hybrid_report.json, evidence_index.json, and run_manifest.json MUST be treated as exports for clients and operators; the application MUST NOT rely on them as the primary source for run status or entity data.  
- **Logs always contain job_id and run_id.** Every log line emitted during job execution (pipeline and ExecuteJobService) MUST include job_id and run_id in structured form (e.g. logger.info(..., extra={"job_id": ..., "run_id": ...})) so that logs are filterable and traceable per run.  
- No se ha introducido cambio breaking en la API pública ni en el formato del reporte híbrido v2.1.  
- La base de código queda más alineada con SOLID, con capas y contratos explícitos, y preparada para evolución hacia v3.0 (escalado, observabilidad, cola distribuida).
