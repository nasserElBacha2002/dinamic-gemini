# Backlog de Ejecución — Versión 2.3

## 1. Objetivo del backlog

Este backlog convierte el **Plan de Implementación v2.3** (`docs/PLAN_V2.3_IMPLEMENTATION.md`) en un conjunto de épicas, historias técnicas y tareas ejecutables. Permite arrancar el desarrollo de forma incremental, con dependencias explícitas, criterios de aceptación verificables y un primer slice de implementación de bajo riesgo. No sustituye el plan: lo operacionaliza para que un equipo técnico pueda priorizar, estimar y ejecutar sin reescribir la arquitectura.

---

## 2. Supuestos de ejecución

- **Refactor incremental:** No hay reescritura total; se extrae y se mueve lógica existente manteniendo comportamiento.
- **Compatibilidad funcional preservada:** Misma API HTTP, mismos reportes (hybrid_report v2.1) y artifacts; los cambios son internos.
- **Interfaces solo cuando esté justificado:** Según la Interface Creation Policy del plan: interfaz solo si hay más de una implementación, si los tests requieren mock, o si es un punto de variabilidad acordado.
- **DB como fuente de verdad en 2.3.C:** Estado del job/run y resultados estructurados se consultan desde la base de datos; no desde archivos.
- **JSON del reporte como salida derivada:** hybrid_report.json, evidence_index.json y run_manifest.json son exports para clientes/operadores; la aplicación no los usa como única fuente para estado o entidades.
- **Estrategia de migración en fases:** Introducir interfaces sin retirar implementaciones actuales; luego adapters que delegan en el código existente; después refactor de consumidores a puertos; por último retirar/reemplazar legacy cuando sea seguro.
- **Tests como guarda:** Tests de humo/E2E antes y después de movimientos importantes; tests de contrato donde se definan puertos.

### 2.1 Clasificación de componentes

Las tareas del backlog deben clasificarse según el tipo de componente que introducen o modifican:

#### Target Architecture
Componentes que representan la arquitectura objetivo del sistema. Son los que se desea mantener a largo plazo.

- **Ejemplos:** RunContext, PipelineStage, servicios de aplicación (CreateJobService, ExecuteJobService), interfaces de repositorio (JobRepository, AnalysisProvider, JobQueue, ArtifactStorage).

#### Migration Adapter
Adaptadores temporales que envuelven componentes legacy mientras la migración está en curso. Delegan en el código existente y deben ser **removibles** cuando el legacy se reemplace por una implementación de arquitectura objetivo.

- **Ejemplos:** JobRepositoryAdapter sobre job_store (implementa JobRepository); ArtifactStorageAdapter sobre lógica actual de escritura a filesystem. En las tareas se debe indicar explícitamente que son adapters de migración y que el componente legacy subyacente sigue siendo la implementación real.

#### Legacy Compatibility
Componentes existentes que deben seguir funcionando durante la migración. No se reemplazan en 2.3; se envuelven o se invocan desde adapters.

- **Ejemplos:** job_store (create_job, get_job, update_job), cola en memoria actual, escritura directa a `Path` en etapas, GeminiProvider/GeminiGlobalAnalyzer.

Las tareas del backlog que introducen o modifican componentes deben dejar claro a qué categoría pertenecen (p. ej. en la descripción de la tarea o en el acceptance criteria: "Adapter de migración sobre job_store; legacy permanece como fuente de verdad hasta fase 4").

---

## 3. Épicas

### Etapa 2.3.A — Core Structural Refactor

| Epic | Título | Objetivo | Alcance | Por qué importa | Dependencias |
|------|--------|----------|---------|-----------------|--------------|
| **EPIC-2.3A-01** | RunContext & Stage Contract | Centralizar estado del run y definir contrato de etapas | RunContext en `src/pipeline/context/run_context.py`, protocolo PipelineStage en `src/pipeline/contracts/stage.py` | Elimina parámetros dispersos y establece firma homogénea para etapas; base para todo el refactor del pipeline | Ninguna |
| **EPIC-2.3A-02** | Pipeline Stages Extraction & Orchestration | Extraer las 6 etapas desde `_run_hybrid` y orquestar por RunContext | InputPreparation, FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting en `src/pipeline/stages/`; orquestador en `HybridInventoryPipeline` | Permite testear y sustituir cada fase; pipeline deja de ser monolítico | EPIC-2.3A-01 |
| **EPIC-2.3A-03** | Application Services (CreateJobService, ExecuteJobService) | Introducir capa de aplicación para creación y ejecución de jobs | CreateJobService y ExecuteJobService en `src/application/services/`; DTOs CreateJobCommand/CreateJobResult | Separa transporte (API/worker) de caso de uso; worker y endpoint se vuelven finos | EPIC-2.3A-02 para ExecuteJobService |
| **EPIC-2.3A-04** | Thin Endpoint & Worker | Dejar que la API solo traduzca HTTP↔comando y el worker solo consuma cola y llame al servicio | `src/api/routes/jobs.py`, `src/jobs/worker.py` | Completa la separación de responsabilidades y reduce riesgo de regresión en rutas/worker | EPIC-2.3A-03 |

### Etapa 2.3.B — Contracts, Interfaces & Dependency Inversion

| Epic | Título | Objetivo | Alcance | Por qué importa | Dependencias |
|------|--------|----------|---------|-----------------|--------------|
| **EPIC-2.3B-01** | Analysis Provider Contract & Adapters | Definir puerto AnalysisProvider y adaptar Gemini | Puertos y DTOs en `src/application/ports/` o `src/pipeline/contracts/`; GeminiAnalysisProvider en infraestructura | OCP/DIP; pipeline no depende del SDK de Gemini | EPIC-2.3A-02 |
| **EPIC-2.3B-02** | Job Persistence & Queue Ports | Definir JobRepository y JobQueue; adaptadores sobre job_store y cola actual | JobRepository, JobQueue; adapters en `src/jobs/adapters/` o equivalente | Testabilidad y preparación para cola persistente | EPIC-2.3A-03 |
| **EPIC-2.3B-03** | Artifact Storage & Stage DTOs | ArtifactStorage y DTOs tipados entre etapas | ArtifactStorage en ports; DTOs PreparedInput, FrameBundleResult, RawAnalysisResult, etc.; EvidenceStage/ReportingStage usan storage | Contratos explícitos entre etapas; escritura de artifacts desacoplada | EPIC-2.3A-02, EPIC-2.3B-01 |
| **EPIC-2.3B-04** | Pipeline & Services Dependency Injection | Inyectar puertos en pipeline y servicios; compositor/bootstrap | Refactor de constructores; módulo de composición (app o bootstrap) que instancia implementaciones y las inyecta | El sistema corre a través de abstracciones; implementaciones sustituibles | EPIC-2.3B-01, EPIC-2.3B-02, EPIC-2.3B-03 |

#### Interface Prioritization (Stage 2.3.B)

En la etapa 2.3.B se introducen varias interfaces. Para evitar bloqueos y sobrecarga, se distingue entre obligatorias y opcionales:

**Obligatorias para cerrar 2.3.B:**

- **AnalysisProvider** — El pipeline debe depender de este puerto para el análisis global; implementación Gemini detrás del adapter.
- **JobRepository** — CreateJobService y ExecuteJobService deben depender de este puerto para persistencia de jobs.
- **JobQueue** — CreateJobService y worker deben depender de este puerto para encolado y consumo.
- **ArtifactStorage** — Etapas de evidencia y reporte deben usar este puerto para escribir JSON/artifacts.

**Opcionales o condicionales:**

- **PromptBuilder** — Útil si se quiere extraer la construcción del prompt del pipeline/provider; no es requisito para considerar 2.3.B cerrado. No debe retrasar el cierre de la etapa.
- **Abstracción estricta de FrameSource** (FrameCollectionRequest/FrameCollectionResult) — El protocolo FrameSource ya existe; endurecer con tipos de request/result es opcional según Interface Creation Policy (segunda implementación o necesidad de mock). No debe retrasar el cierre de 2.3.B.

Las abstracciones opcionales pueden implementarse después de que los cuatro puertos obligatorios estén definidos, inyectados y cubiertos por tests de contrato. La prioridad es cerrar 2.3.B con AnalysisProvider, JobRepository, JobQueue y ArtifactStorage.

### Etapa 2.3.C — Execution Reliability, Persistence & Auditability

| Epic | Título | Objetivo | Alcance | Por qué importa | Dependencias |
|------|--------|----------|---------|-----------------|--------------|
| **EPIC-2.3C-01** | Run Lifecycle & Persistence | Modelo Run, repositorios de runs/errores/artifacts/etapas; ExecuteJobService con ciclo de vida de run | RunRecord, RunRepository; RunErrorRecord, RunErrorRepository; RunArtifactRecord, RunStageExecutionRecord; refactor ExecuteJobService | Auditoría, fuente de verdad en DB, invariantes operativos | EPIC-2.3B-04 |
| **EPIC-2.3C-02** | Structured Logging & Run Manifest | Logging con job_id/run_id/stage; run_manifest.json | Helper o wrapper de logger; generación de run_manifest.json en run_dir | Observabilidad y trazabilidad sin depender solo de archivos | EPIC-2.3A-02; puede adelantarse en parte |
| **EPIC-2.3C-03** | API/Worker Separation & Documentation | Documentar y opcionalmente separar entrypoint del worker | Documentación; opcional `python -m src.worker` sin API | Claridad operativa y preparación para despliegue separado | Ninguna (independiente) |

---

## 4. Historias técnicas

### EPIC-2.3A-01 — RunContext & Stage Contract

#### STORY-2.3A-01
- **Title:** Introduce RunContext and remove cross-cutting execution parameters
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-01
- **Description:** Crear el objeto RunContext que agrupe job_id, run_id, workspace_path, run_dir, job_input, settings, logger, progress_callback y metadata. El pipeline y las etapas dejarán de recibir estos parámetros por separado o por kwargs.
- **Technical value:** Un solo objeto de contexto compartido; menos acoplamiento y firma estable para futuras etapas.
- **Acceptance criteria:**
  - Existe `src/pipeline/context/run_context.py` con RunContext (dataclass o clase) con los campos definidos en el plan.
  - RunContext no se usa como contenedor mutable de salidas de etapas; solo metadata, paths, config, logger y callback.
- **Dependencies:** Ninguna.
- **Risk:** Low.

#### STORY-2.3A-02
- **Title:** Define PipelineStage protocol for homogeneous stage interface
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-01
- **Description:** Crear el protocolo PipelineStage con método run(context: RunContext, data: TIn) -> TOut en `src/pipeline/contracts/stage.py`. Los tipos pueden ser permisivos (Any o dataclasses mínimos) en 2.3.A.
- **Technical value:** Firma común para todas las etapas; orquestador puede invocar etapas en secuencia sin conocer implementación concreta.
- **Acceptance criteria:**
  - Existe `src/pipeline/contracts/stage.py` con PipelineStage (Protocol).
  - Todas las etapas futuras cumplirán run(context, data) -> result.
- **Dependencies:** STORY-2.3A-01 (RunContext existente).
- **Risk:** Low.

---

### EPIC-2.3A-02 — Pipeline Stages Extraction & Orchestration

#### STORY-2.3A-03
- **Title:** Extract InputPreparationStage from _run_hybrid
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02
- **Description:** Extraer la lógica de validación de input_type y preparación de run_dir y rutas desde el inicio de _run_hybrid a una etapa InputPreparationStage que devuelva PreparedInput (dataclass mínimo).
- **Technical value:** Primera etapa explícita; reduce complejidad del orquestador.
- **Acceptance criteria:**
  - InputPreparationStage.run(context, initial_input) devuelve PreparedInput con campos necesarios para la siguiente etapa.
  - La lógica extraída ya no está duplicada en _run_hybrid.
- **Dependencies:** STORY-2.3A-01, STORY-2.3A-02.
- **Risk:** Low.

#### STORY-2.3A-04
- **Title:** Extract FrameAcquisitionStage from _run_hybrid
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02
- **Description:** Extraer normalización de fotos (si input_type==photos), get_frame_source, get_frames y carga de imágenes con límite a FrameAcquisitionStage; salida FrameBundleResult (frames, frame_refs, metadata).
- **Technical value:** Etapa de adquisición de frames aislada y testeable.
- **Acceptance criteria:**
  - FrameAcquisitionStage.run(context, prepared_input) devuelve FrameBundleResult.
  - Comportamiento idéntico al actual (mismos frames y metadata).
- **Dependencies:** STORY-2.3A-03.
- **Risk:** Medium (posible regresión en frame indices o límites).

#### STORY-2.3A-05
- **Title:** Extract AnalysisStage from _run_hybrid
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02
- **Description:** Extraer obtención del provider, construcción de LLMRequest, llamada a analyze_global a AnalysisStage; salida RawAnalysisResult (parsed_json, provider_name).
- **Technical value:** Análisis LLM aislado; base para luego inyectar AnalysisProvider en 2.3.B.
- **Acceptance criteria:**
  - AnalysisStage.run(context, frame_bundle_result) devuelve RawAnalysisResult.
  - No se cambia la forma de invocar al provider en 2.3.A (se puede seguir usando get_llm_provider).
- **Dependencies:** STORY-2.3A-04.
- **Risk:** Medium.

#### STORY-2.3A-06
- **Title:** Extract EntityResolutionStage from _run_hybrid
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02
- **Description:** Extraer parse_entities, sort_entities_deterministically, resolve_pallet_id, assign_count_status, compute_entity_quality_score a EntityResolutionStage; salida ResolvedEntitiesResult (entities).
- **Technical value:** Resolución de entidades en una etapa con contrato claro.
- **Acceptance criteria:**
  - EntityResolutionStage.run(context, raw_analysis_result) devuelve ResolvedEntitiesResult.
  - Determinismo y reglas de count_status/quality_score preservados.
- **Dependencies:** STORY-2.3A-05.
- **Risk:** Medium.

#### STORY-2.3A-07
- **Title:** Extract EvidenceStage and ReportingStage from _run_hybrid
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02
- **Description:** Extraer generate_evidence_pack a EvidenceStage (salida EvidenceResult) y build_hybrid_report + write_json a ReportingStage (salida ReportingResult con report_path, summary).
- **Technical value:** Evidencia y reporte como etapas explícitas; cierre del flujo por DTOs.
- **Acceptance criteria:**
  - EvidenceStage.run(context, resolved_entities) devuelve EvidenceResult.
  - ReportingStage.run(context, report_stage_input con resolved + evidence) devuelve ReportingResult; hybrid_report.json se escribe en run_dir.
- **Dependencies:** STORY-2.3A-06.
- **Risk:** Low.

#### STORY-2.3A-08
- **Title:** Refactor HybridInventoryPipeline to orchestrate stages with RunContext
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02
- **Description:** Refactorizar _run_hybrid para que reciba RunContext (creado fuera o en método público), instancie o reciba las 6 etapas, las ejecute en secuencia pasando el resultado de una a la siguiente, y devuelva 0/1 según ReportingResult. Eliminar la lógica inline ya movida a etapas.
- **Technical value:** Orquestador delgado; flujo de datos solo por valores de retorno, no por RunContext.
- **Acceptance criteria:**
  - Pipeline tiene método que acepta RunContext (ej. run(context) o process(context)).
  - Datos fluyen: prepared → frames → analysis → resolved → evidence → report. RunContext solo se usa para paths, settings, logger, progress.
  - No queda lógica de etapas duplicada en el orquestador.
- **Dependencies:** STORY-2.3A-03 a STORY-2.3A-07.
- **Risk:** Medium.

#### Pipeline Stage Extraction Strategy

Las extracciones de etapas del pipeline (InputPreparationStage, FrameAcquisitionStage, AnalysisStage, EntityResolutionStage, EvidenceStage, ReportingStage) deben tratarse como **un refactor secuencial coordinado**, no como tareas independientes en paralelo.

- **Mismo núcleo de orquestación:** Todas estas historias modifican la misma lógica central (`_run_hybrid` / orquestador en `HybridInventoryPipeline`). Implementarlas en paralelo genera estados intermedios inestables y dificulta las pruebas.
- **Conflictos de integración:** Si varias ramas refactorizan el pipeline a la vez, los conflictos de merge son altos y el resultado puede ser inconsistente (doble invocación, datos no pasados correctamente entre etapas).
- **Orden recomendado de extracción:**  
  1. InputPreparationStage  
  2. FrameAcquisitionStage  
  3. AnalysisStage  
  4. EntityResolutionStage  
  5. EvidenceStage  
  6. ReportingStage  

Cada extracción debe **dejar el pipeline en estado ejecutable** antes de pasar a la siguiente: tras extraer una etapa, el orquestador invoca esa etapa y pasa su resultado al bloque restante (o a la siguiente etapa ya extraída); se ejecutan los tests acordados (baseline smoke test y los que apliquen) y solo entonces se inicia la extracción de la siguiente etapa.

#### Baseline Pipeline Smoke Test

Antes de iniciar el refactor estructural del pipeline (extracción de etapas), debe existir un **test de humo de baseline** que:

- Ejecute el pipeline actual de punta a punta (con input mínimo válido: video corto o conjunto pequeño de fotos).
- Valide que el pipeline produce una salida mínima válida (p. ej. que existe `hybrid_report.json` con estructura esperada y que el código de retorno es el esperado).
- Sirva como **guarda de regresión** durante toda la extracción de etapas en 2.3.A.

Este test de humo **debe permanecer en verde** en todos los refactors de 2.3.A. Si en algún momento deja de pasar, debe corregirse antes de continuar con la siguiente extracción. Se recomienda añadir o formalizar este test como parte de los prerrequisitos del primer slice (o como TASK explícita antes de STORY-2.3A-03).

---

### EPIC-2.3A-03 — Application Services

#### STORY-2.3A-09
- **Title:** Implement CreateJobService with CreateJobCommand and CreateJobResult
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-03
- **Description:** Crear CreateJobCommand y CreateJobResult (en application/commands y results o en el módulo del servicio). Implementar CreateJobService.execute(command): validación, persistencia de archivos (reutilizar persist_photos_from_uploads y lógica de video), creación de directorios, create_job(job_store), enqueue(job_id); devolver CreateJobResult.
- **Technical value:** Caso de uso de creación en un solo lugar; endpoint podrá delegar sin lógica de negocio.
- **Acceptance criteria:**
  - CreateJobService recibe comando tipado y devuelve resultado tipado con job_id, status, mode, confidence_threshold.
  - Toda la lógica de validación, persistencia y encolado está en el servicio.
- **Dependencies:** Ninguna (independiente del pipeline).
- **Risk:** Low.

#### STORY-2.3A-10
- **Title:** Refactor POST /jobs to delegate to CreateJobService
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-04
- **Description:** En create_inventory_job (api/routes/jobs.py), construir CreateJobCommand desde request.form(), llamar create_job_service.execute(command), mapear a JobCreateResponse y devolver 202. Eliminar lógica de negocio y persistencia del endpoint.
- **Technical value:** Endpoint fino; transporte separado de caso de uso.
- **Acceptance criteria:**
  - El endpoint no contiene validación de negocio ni persistencia de archivos; solo traducción HTTP → comando → resultado.
- **Dependencies:** STORY-2.3A-09.
- **Risk:** Low.

#### STORY-2.3A-11
- **Title:** Implement ExecuteJobService with RunContext and pipeline invocation
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-03
- **Description:** Implementar ExecuteJobService.execute(job_id): get_job, comprobar QUEUED, update_job RUNNING, construir RunContext (run_dir, logger, progress_cb, etc.), instanciar pipeline y llamar run(context), según retorno update_job SUCCEEDED/FAILED y output; en éxito invocar la lógica actual de _push_success_to_db (moverla a colaborador o al servicio).
- **Technical value:** Caso de uso de ejecución en un solo lugar; worker podrá limitarse a dequeue y llamar al servicio.
- **Acceptance criteria:**
  - ExecuteJobService orquesta carga de job, RunContext, pipeline y actualización de estado/resultado.
  - La lógica de _push_success_to_db vive en el servicio o en un colaborador, no en el worker.
- **Dependencies:** STORY-2.3A-08 (pipeline que acepta RunContext).
- **Risk:** Medium.

#### STORY-2.3A-12
- **Title:** Refactor worker to only call ExecuteJobService
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-04
- **Description:** Refactorizar run_job en jobs/worker.py para que solo llame execute_job_service.execute(job_id). El worker_loop sigue dequeue → run_job. Obtener base_path de config si hace falta o mantener parámetro según integración con server.
- **Technical value:** Worker sin lógica de negocio; solo adaptador de cola a servicio.
- **Acceptance criteria:**
  - run_job no contiene lógica de carga de job, construcción de RunContext, actualización de estado ni lectura del reporte para DB.
- **Dependencies:** STORY-2.3A-11.
- **Risk:** Low.

#### STORY-2.3A-13
- **Title:** Integration tests for full flow (create job, execute, report and evidence)
- **Stage:** 2.3.A
- **Epic:** EPIC-2.3A-02 / EPIC-2.3A-04
- **Description:** Añadir o ajustar tests de integración que ejecuten el flujo completo: crear job (video o fotos), ejecutar (vía ExecuteJobService o worker), comprobar que hybrid_report.json y evidence (evidence_index.json) existen y que la estructura del reporte no cambia (entities, report_version). Opcionalmente tests unitarios por etapa con RunContext y datos de prueba.
- **Technical value:** Guarda contra regresiones funcionales tras el refactor.
- **Acceptance criteria:**
  - Al menos un E2E/smoke test que cubra create + execute y valide reporte y evidencia.
  - Tests de etapa que invoquen stage.run(context, input_data) y comprueben tipo y campos clave del resultado.
- **Dependencies:** STORY-2.3A-10, STORY-2.3A-12.
- **Risk:** Low.

---

### EPIC-2.3B-01 — Analysis Provider Contract & Adapters

#### STORY-2.3B-01
- **Title:** Define AnalysisProvider port and DTOs (AnalysisRequest, AnalysisResponse)
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-01
- **Description:** Definir en src/application/ports/ (o pipeline/contracts) el protocolo AnalysisProvider con analyze(request: AnalysisRequest) -> AnalysisResponse. Definir AnalysisRequest (run_id, prompt, schema_version, imágenes, metadata) y AnalysisResponse (provider_name, model_name, raw_text, parsed_payload, usage, latency_ms, warnings). Incluir AnalysisImage si aplica.
- **Technical value:** Contrato estable para cualquier implementación (Gemini, Fake, futuro OpenAI).
- **Acceptance criteria:**
  - Puertos y DTOs definidos; documentación de precondiciones/postcondiciones si es necesario.
- **Dependencies:** EPIC-2.3A-02 completado.
- **Risk:** Low.

#### STORY-2.3B-02
- **Title:** Implement GeminiAnalysisProvider implementing AnalysisProvider
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-01
- **Description:** Crear GeminiAnalysisProvider que implemente AnalysisProvider, envolviendo la lógica actual de GeminiProvider/GeminiGlobalAnalyzer; recibe AnalysisRequest y devuelve AnalysisResponse; mapear excepciones del SDK a tipo de error de dominio/contrato.
- **Technical value:** Pipeline puede depender del puerto sin importar Gemini.
- **Acceptance criteria:**
  - GeminiAnalysisProvider implementa el protocolo; el pipeline no importa el módulo Gemini directamente.
- **Dependencies:** STORY-2.3B-01.
- **Risk:** Medium (LSP: asegurar que todos los campos requeridos están presentes).

#### STORY-2.3B-03
- **Title:** Refactor AnalysisStage to use injected AnalysisProvider and DTOs
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-01
- **Description:** Refactorizar AnalysisStage para recibir AnalysisProvider por constructor, recibir FrameBundleResult y devolver RawAnalysisResult usando AnalysisRequest/AnalysisResponse; no pasar dict ni respuestas crudas del SDK.
- **Technical value:** Etapa de análisis desacoplada del proveedor concreto.
- **Acceptance criteria:**
  - AnalysisStage recibe y devuelve DTOs; se invoca provider.analyze(request).
- **Dependencies:** STORY-2.3B-02.
- **Risk:** Low.

#### STORY-2.3B-04
- **Title:** Contract tests for AnalysisProvider
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-01
- **Description:** Tests que verifiquen que una implementación (FakeProvider o GeminiAnalysisProvider) acepta AnalysisRequest y devuelve AnalysisResponse con campos requeridos y tipos correctos.
- **Technical value:** Garantiza que implementaciones alternativas no rompen el pipeline.
- **Dependencies:** STORY-2.3B-03.
- **Risk:** Low.

---

### EPIC-2.3B-02 — Job Persistence & Queue Ports

#### STORY-2.3B-05
- **Title:** Define JobRepository and adapter over job_store
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-02
- **Description:** Definir protocolo JobRepository (create(job_record), get(job_id) -> JobRecord | None, update(job_id, updates)). Implementar adaptador que delegue en create_job, get_job, update_job del job_store.
- **Technical value:** Servicios dependen de puerto; tests pueden usar dobles.
- **Acceptance criteria:**
  - JobRepository definido; adaptador implementado y usable desde CreateJobService y ExecuteJobService.
- **Dependencies:** EPIC-2.3A-03.
- **Risk:** Low.

#### STORY-2.3B-06
- **Title:** Define JobQueue and InMemoryJobQueue adapter
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-02
- **Description:** Definir protocolo JobQueue (enqueue(job_id), dequeue(timeout) -> job_id | None). Implementar InMemoryJobQueue en src/infrastructure/queue/ o jobs/adapters que delegue en la cola actual.
- **Technical value:** Worker y CreateJobService dependen del puerto; preparación para cola persistente.
- **Acceptance criteria:**
  - JobQueue definido; InMemoryJobQueue implementado; enqueue/dequeue con semántica documentada (orden, timeout).
- **Dependencies:** Ninguna dentro de 2.3.B.
- **Risk:** Low.

#### STORY-2.3B-07
- **Title:** Contract tests for JobRepository and JobQueue
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-02
- **Description:** Tests de contrato: create luego get devuelve el mismo job; enqueue luego dequeue devuelve el mismo job_id; comportamiento de timeout de dequeue.
- **Technical value:** Adaptadores y futuras implementaciones se comportan de forma consistente.
- **Dependencies:** STORY-2.3B-05, STORY-2.3B-06.
- **Risk:** Low.

---

### EPIC-2.3B-03 — Artifact Storage & Stage DTOs

#### STORY-2.3B-08
- **Title:** Define ArtifactStorage and FileSystemArtifactStorage
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-03
- **Description:** Definir protocolo ArtifactStorage (write_json(relative_path, payload), write_bytes(relative_path, content, content_type), exists(relative_path)). Implementar FileSystemArtifactStorage que escriba bajo run_dir.
- **Technical value:** Etapas de evidencia y reporte no escriben directamente a Path; sustituible en tests.
- **Acceptance criteria:**
  - ArtifactStorage definido; FileSystemArtifactStorage implementado.
- **Dependencies:** EPIC-2.3A-02.
- **Risk:** Low.

#### STORY-2.3B-09
- **Title:** Harden stage DTOs and use ArtifactStorage in EvidenceStage and ReportingStage
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-03
- **Description:** Asegurar que todas las etapas usen DTOs tipados (PreparedInput, FrameBundleResult, RawAnalysisResult, ResolvedEntitiesResult, EvidenceResult, ReportingResult). EvidenceStage y ReportingStage usan ArtifactStorage para escribir JSON (o al menos el puerto con implementación que escribe en run_dir).
- **Technical value:** Contratos explícitos entre etapas; sin dict ambiguos; escritura de artifacts desacoplada.
- **Acceptance criteria:**
  - No se pasan dict sin tipo entre etapas; EvidenceStage/ReportingStage usan ArtifactStorage inyectado.
- **Dependencies:** STORY-2.3B-08; DTOs ya existentes en 2.3.A pueden endurecerse aquí.
- **Risk:** Low.

#### STORY-2.3B-10
- **Title:** Optional: FrameSource request/result types and PromptBuilder
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-03
- **Description:** Endurecer FrameSource con FrameCollectionRequest/FrameCollectionResult (o reutilizar FramesBundle); adaptar VideoFrameSource y PhotosFrameSource. Opcional: definir PromptBuilder y PromptPayload; extraer construcción del prompt a InventoryPromptBuilder.
- **Technical value:** Contratos completos para frame source y prompt; OCP para futuros proveedores o prompts.
- **Acceptance criteria:**
  - FrameSource con entrada/salida tipadas si el plan lo incluye; PromptBuilder opcional según Interface Creation Policy.
- **Dependencies:** STORY-2.3A-04 (FrameAcquisitionStage).
- **Risk:** Low.

---

### EPIC-2.3B-04 — Pipeline & Services Dependency Injection

#### STORY-2.3B-11
- **Title:** Refactor services and pipeline to accept ports via constructor; composition root
- **Stage:** 2.3.B
- **Epic:** EPIC-2.3B-04
- **Description:** Refactorizar CreateJobService y ExecuteJobService para recibir JobRepository (y CreateJobService también JobQueue) por constructor. Refactorizar orquestador y etapas para recibir AnalysisProvider, ArtifactStorage, FrameSource (o factory) por constructor. Crear módulo de composición (bootstrap o en app) que instancie implementaciones concretas e inyecte en servicios y pipeline.
- **Technical value:** Sistema corre a través de interfaces; implementaciones sustituibles y testeables.
- **Acceptance criteria:**
  - Pipeline y servicios no instancian ni importan Gemini, job_store, queue, filesystem directamente; dependen de puertos inyectados.
  - Compositor único donde se ensamblan adaptadores y servicios.
- **Dependencies:** STORY-2.3B-03, STORY-2.3B-05, STORY-2.3B-06, STORY-2.3B-09.
- **Risk:** Medium (asegurar que todo el wiring es correcto y tests E2E pasan).

---

#### Run Status Semantics (Stage 2.3.C)

El estado de una ejecución (Run) debe interpretarse de forma unívoca para operación y auditoría.

| Scenario | Run Status | Description |
|----------|------------|-------------|
| Resultados estructurados persistidos correctamente y artifacts generados | **SUCCEEDED** | Ejecución completada con éxito; estado y resultados consultables en DB; artifacts (reporte JSON, evidencia) disponibles. |
| Resultados estructurados persistidos pero falló la exportación de artifacts | **PARTIAL** | La ejecución produjo resultado válido y se persistió en DB, pero la generación de algún artifact (p. ej. hybrid_report.json) falló. El run no debe marcarse SUCCEEDED sin artifacts si el contrato operativo exige ambos; se marca PARTIAL para indicar éxito parcial. |
| Resultados estructurados no persistidos | **FAILED** | La ejecución no pudo producir un resultado válido o no se pudo persistir en la fuente de verdad. No hay estado SUCCEEDED ni PARTIAL sin persistencia estructurada. |

Reglas:

- **Persistencia de resultados estructurados es el criterio crítico de éxito.** Sin escritura en runs/run_entities (o equivalente) en DB, el run no puede ser SUCCEEDED.
- **Generación de artifacts es secundaria** para el estado del run: si los datos ya están en DB pero falla escribir el JSON, el run es PARTIAL (o FAILED si se considera crítico en el diseño).
- **Cualquier error de ejecución debe producir entradas RunErrorRecord.** Fallos en pipeline, en ExecuteJobService o en persistencia deben traducirse en un registro en run_errors con run_id, stage_name, error_code, message, para que toda falla sea auditable.

---

### EPIC-2.3C-01 — Run Lifecycle & Persistence

#### STORY-2.3C-01
- **Title:** RunRecord model and RunRepository (create_for_job, get, mark_*)
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-01
- **Description:** Definir RunRecord (run_id, job_id, status, engine_version, schema_version, provider_name, provider_model, started_at, finished_at, duration_ms, effective_config_snapshot, warning_count, error_code, error_message). Tabla runs y RunRepository con create_for_job, get, mark_running, mark_succeeded, mark_failed.
- **Technical value:** Entidad Run como base para auditoría y fuente de verdad de estado.
- **Acceptance criteria:**
  - RunRecord y RunRepository existentes; cuando DB está habilitada, se persiste en tabla runs.
- **Dependencies:** EPIC-2.3B-04.
- **Risk:** Low.

#### STORY-2.3C-02
- **Title:** RunErrorRecord and RunErrorRepository
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-01
- **Description:** Modelo RunErrorRecord (run_id, stage_name, error_code, error_type, message, details, retriable, occurred_at); tabla run_errors; RunErrorRepository (save).
- **Technical value:** Todos los fallos de ejecución producen un registro auditable.
- **Acceptance criteria:**
  - Cualquier fallo en pipeline o ExecuteJobService persiste RunErrorRecord.
- **Dependencies:** STORY-2.3C-01.
- **Risk:** Low.

#### STORY-2.3C-03
- **Title:** RunStageExecutionRecord and RunArtifactRecord with repositories
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-01
- **Description:** Modelos RunStageExecutionRecord y RunArtifactRecord; tablas run_stage_executions y run_artifacts; RunStageRepository (save), RunArtifactRepository (save, list_by_run).
- **Technical value:** Trazabilidad por etapa y referencia a artifacts desde DB.
- **Acceptance criteria:**
  - Repositorios disponibles para que ExecuteJobService registre etapas y artifacts.
- **Dependencies:** STORY-2.3C-01.
- **Risk:** Low.

#### STORY-2.3C-04
- **Title:** ExecuteJobService run lifecycle: create Run, persist result from DTOs, mark status
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-01
- **Description:** Refactorizar ExecuteJobService: al iniciar, crear Run y marcarlo RUNNING; al finalizar con éxito, persistir resultado desde DTOs (ResolvedEntitiesResult, ReportingResult) en runs y tablas relacionadas (run_entities o equivalente), marcar run SUCCEEDED y job SUCCEEDED; en excepción, persistir RunErrorRecord, marcar run y job FAILED. Respetar invariantes: no SUCCEEDED sin resultados estructurados persistidos; artifact export failures → PARTIAL/FAILED; cuando DB está habilitada, estado desde DB.
- **Technical value:** DB como fuente de verdad; resultado no depende de leer hybrid_report.json.
- **Acceptance criteria:**
  - Los datos que hoy se extraen de hybrid_report.json para set_job_outputs e insert_pallet_results se obtienen de DTOs y se persisten en runs/run_entities; el reporte JSON se sigue generando como artifact.
  - Cumplimiento de Operational Consistency Rules del plan.
- **Dependencies:** STORY-2.3C-01, STORY-2.3C-02, STORY-2.3C-03.
- **Risk:** High (migración de lógica de persistencia; compatibilidad sin DB).

#### STORY-2.3C-05
- **Title:** Run lifecycle and persistence tests
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-01
- **Description:** Tests que cubran: run creado y marcado RUNNING al iniciar; run marcado SUCCEEDED cuando el pipeline termina y el resultado estructurado está persistido; run marcado FAILED cuando hay error y RunErrorRecord persistido. Verificar que los datos de resultado se persisten en DB y no solo en JSON. Al menos un test de fallo (pipeline o provider lanza) con RunErrorRecord y run/job FAILED.
- **Technical value:** Garantiza que las reglas operativas se cumplen.
- **Dependencies:** STORY-2.3C-04.
- **Risk:** Low.

---

### EPIC-2.3C-02 — Structured Logging & Run Manifest

#### STORY-2.3C-06
- **Title:** Structured logging with job_id, run_id, stage
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-02
- **Description:** Introducir módulo o helper que reciba job_id, run_id, stage y emita logs con esos campos en extra (o atributos estructurados). Usar en pipeline y ExecuteJobService.
- **Technical value:** Logs filtrables y trazables por run.
- **Acceptance criteria:**
  - Cada log emitido durante la ejecución incluye job_id y run_id (y stage/event cuando aplique) en forma estructurada.
- **Dependencies:** EPIC-2.3A-02 (pipeline con RunContext).
- **Risk:** Low.

#### STORY-2.3C-07
- **Title:** Generate and write run_manifest.json; optional stage execution records
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-02
- **Description:** Generar y escribir run_manifest.json en run_dir con run_id, job_id, engine_version, provider, input summary, frames count, stages, warnings, artifact refs, result_summary. Opcionalmente registrar el artifact en RunArtifactRepository. Instrumentar etapas u orquestador para persistir StageExecutionRecord (started_at, finished_at, duration_ms, resumen input/output) vía RunStageRepository.
- **Technical value:** Manifest como artifact de trazabilidad; etapas auditables.
- **Acceptance criteria:**
  - run_manifest.json existe al finalizar el run; opcionalmente run_stage_executions poblado.
- **Dependencies:** STORY-2.3C-03, STORY-2.3C-04.
- **Risk:** Low.

---

### EPIC-2.3C-03 — API/Worker Separation

#### STORY-2.3C-08
- **Title:** Document API and worker as separate components; optional worker entrypoint
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-03
- **Description:** Documentar que API y worker son componentes separables. Opcionalmente implementar entrypoint `python -m src.worker` que solo ejecute el loop de cola sin arrancar la API; el servidor puede seguir arrancando el worker en thread por defecto con opción de desactivar para despliegue separado.
- **Technical value:** Claridad operativa y preparación para despliegue independiente del worker.
- **Acceptance criteria:**
  - Documentación actualizada; entrypoint opcional implementado si se desea.
- **Dependencies:** Ninguna.
- **Risk:** Low.

---

### Migraciones y schema (2.3.C)

#### STORY-2.3C-09
- **Title:** Schema migrations for runs, run_errors, run_stage_executions, run_artifacts
- **Stage:** 2.3.C
- **Epic:** EPIC-2.3C-01
- **Description:** Scripts o migraciones SQL para crear tablas runs, run_errors, run_stage_executions, run_artifacts (y run_entities si se persisten entidades por run). Asegurar que cuando sqlserver_enabled es false, el sistema siga operativo (Run en memoria o solo run_manifest.json).
- **Technical value:** Despliegue con nuevas tablas sin romper entornos sin DB.
- **Acceptance criteria:**
  - Migraciones aplicables; comportamiento sin DB documentado y probado.
- **Dependencies:** STORY-2.3C-01, STORY-2.3C-02, STORY-2.3C-03.
- **Risk:** Medium (compatibilidad con despliegues actuales).

---

## 5. Tareas técnicas por historia

### STORY-2.3A-01
- **TASK-2.3A-01.1** — Crear `src/pipeline/context/run_context.py` con dataclass/clase RunContext (job_id, run_id, workspace_path, run_dir, job_input, settings, logger, progress_callback, metadata). *Salida:* Módulo importable con RunContext.
- **TASK-2.3A-01.2** — Documentar en código que RunContext no debe usarse para salidas de etapas; solo metadata, paths, config, logger, callback. *Salida:* Docstrings/clarificación en plan o en código.

### STORY-2.3A-02
- **TASK-2.3A-02.1** — Crear `src/pipeline/contracts/stage.py` con protocolo PipelineStage (run(context, data) -> result); opcional TIn, TOut genéricos. *Salida:* Protocolo usable por etapas.

### STORY-2.3A-03
- **TASK-2.3A-03.1** — Definir PreparedInput (dataclass) con campos necesarios para FrameAcquisitionStage. *Salida:* DTO en pipeline/dto o stages. *Módulo sugerido:* `src/pipeline/stages/input_preparation_stage.py` o `src/pipeline/dto/`.
- **TASK-2.3A-03.2** — Implementar InputPreparationStage en `src/pipeline/stages/input_preparation_stage.py`: validar input_type, preparar run_dir y rutas; run(context, initial_input) -> PreparedInput. *Salida:* Etapa que cumple PipelineStage.
- **TASK-2.3A-03.3** — Eliminar del inicio de _run_hybrid la lógica movida a InputPreparationStage. *Salida:* _run_hybrid sin duplicado (todavía invoca lógica en línea hasta STORY-2.3A-08).

### STORY-2.3A-04
- **TASK-2.3A-04.1** — Definir FrameBundleResult (frames, frame_refs, metadata). *Salida:* DTO en pipeline/dto o stages.
- **TASK-2.3A-04.2** — Implementar FrameAcquisitionStage en `src/pipeline/stages/frame_acquisition_stage.py`: normalización fotos, get_frame_source, get_frames, carga con límite; run(context, prepared_input) -> FrameBundleResult. *Salida:* Etapa implementada.
- **TASK-2.3A-04.3** — Eliminar de _run_hybrid la lógica movida a FrameAcquisitionStage.

### STORY-2.3A-05
- **TASK-2.3A-05.1** — Definir RawAnalysisResult (parsed_json, provider_name). *Salida:* DTO.
- **TASK-2.3A-05.2** — Implementar AnalysisStage en `src/pipeline/stages/analysis_stage.py`: get_llm_provider, construir LLMRequest, analyze_global; run(context, frame_bundle_result) -> RawAnalysisResult. *Salida:* Etapa implementada.
- **TASK-2.3A-05.3** — Eliminar de _run_hybrid la lógica movida a AnalysisStage.

### STORY-2.3A-06
- **TASK-2.3A-06.1** — Definir ResolvedEntitiesResult (entities). *Salida:* DTO.
- **TASK-2.3A-06.2** — Implementar EntityResolutionStage en `src/pipeline/stages/entity_resolution_stage.py`: parse_entities, sort, resolve_pallet_id, assign_count_status, compute_entity_quality_score; run(context, raw_analysis_result) -> ResolvedEntitiesResult. *Salida:* Etapa implementada.
- **TASK-2.3A-06.3** — Eliminar de _run_hybrid la lógica movida a EntityResolutionStage.

### STORY-2.3A-07
- **TASK-2.3A-07.1** — Definir EvidenceResult y ReportingResult (report_path, summary). *Salida:* DTOs.
- **TASK-2.3A-07.2** — Implementar EvidenceStage en `src/pipeline/stages/evidence_stage.py`: generate_evidence_pack; run(context, resolved_entities) -> EvidenceResult. *Salida:* Etapa implementada.
- **TASK-2.3A-07.3** — Implementar ReportingStage en `src/pipeline/stages/reporting_stage.py`: build_hybrid_report, write_json; run(context, report_stage_input) -> ReportingResult. *Salida:* Etapa implementada.
- **TASK-2.3A-07.4** — Eliminar de _run_hybrid la lógica movida a EvidenceStage y ReportingStage.

### STORY-2.3A-08
- **TASK-2.3A-08.1** — Refactorizar HybridInventoryPipeline: método que recibe RunContext (ej. run(context)); instanciar o recibir por constructor las 6 etapas; ejecutar en secuencia pasando resultado de una a la siguiente; devolver 0/1 según report.success. *Archivos:* `src/pipeline/hybrid_inventory_pipeline.py`. *Salida:* Orquestador que solo orquesta; datos por return values.
- **TASK-2.3A-08.2** — Asegurar que pipeline pueda ser invocado desde fuera con RunContext (ExecuteJobService construye contexto y llama run(context)). *Salida:* API pública del pipeline alineada con uso en servicio.

### STORY-2.3A-09
- **TASK-2.3A-09.1** — Crear CreateJobCommand y CreateJobResult en `src/application/commands/` y `src/application/results/` (o en create_job_service.py). *Salida:* DTOs definidos.
- **TASK-2.3A-09.2** — Implementar CreateJobService en `src/application/services/create_job_service.py`: execute(command) con validación, persistencia (persist_photos_from_uploads + video), directorios, create_job(job_store), enqueue(job_id); return CreateJobResult. *Salida:* Servicio listo para uso desde endpoint.

### STORY-2.3A-10
- **TASK-2.3A-10.1** — En `src/api/routes/jobs.py`, en create_inventory_job: construir CreateJobCommand desde request.form(), llamar create_job_service.execute(command), mapear a JobCreateResponse, return 202. *Salida:* Endpoint sin lógica de negocio ni persistencia.

### STORY-2.3A-11
- **TASK-2.3A-11.1** — Crear ExecuteJobService en `src/application/services/execute_job_service.py`: execute(job_id): get_job, validar QUEUED, update_job RUNNING, construir RunContext, instanciar pipeline, run(context), según retorno update_job SUCCEEDED/FAILED y output; en éxito llamar lógica de _push_success_to_db (mover desde worker a colaborador o al servicio). *Salida:* Caso de uso de ejecución centralizado.
- **TASK-2.3A-11.2** — Ajustar pipeline para ser invocable con RunContext (ya cubierto por TASK-2.3A-08.2 si se hace después).

### STORY-2.3A-12
- **TASK-2.3A-12.1** — En `src/jobs/worker.py`, refactorizar run_job para que solo llame execute_job_service.execute(job_id). Obtener base_path de config si hace falta. *Salida:* Worker sin lógica de carga de job, RunContext, actualización de estado ni _push_success_to_db.

### STORY-2.3A-13
- **TASK-2.3A-13.1** — Añadir o ajustar test E2E: create job (video o fotos), execute (ExecuteJobService o worker), assert hybrid_report.json y evidence_index.json existen, estructura del reporte (entities, report_version) igual. *Archivos:* tests/ (ej. test_e2e_v2_2.py o test_stage4). *Salida:* Test que falle si hay regresión funcional.
- **TASK-2.3A-13.2** — (Opcional) Tests unitarios por etapa: stage.run(context, input_data) con RunContext mínimo y input representativo; assert tipo y campos clave del resultado. *Salida:* Tests de contrato por etapa.

### STORY-2.3B-01
- **TASK-2.3B-01.1** — Definir en `src/application/ports/analysis_provider.py` (o pipeline/contracts): AnalysisProvider (Protocol), AnalysisRequest, AnalysisResponse, AnalysisImage si aplica. *Salida:* Puertos y DTOs importables.

### STORY-2.3B-02
- **TASK-2.3B-02.1** — Crear GeminiAnalysisProvider que implemente AnalysisProvider; envolver lógica de GeminiProvider/GeminiGlobalAnalyzer; mapear excepciones SDK a error de dominio. *Módulo sugerido:* `src/llm/providers/gemini_adapter.py` o similar. *Salida:* Implementación que cumple el contrato.

### STORY-2.3B-03
- **TASK-2.3B-03.1** — Refactorizar AnalysisStage: recibir AnalysisProvider por constructor; convertir FrameBundleResult a AnalysisRequest, llamar provider.analyze(request), convertir AnalysisResponse a RawAnalysisResult. *Archivos:* `src/pipeline/stages/analysis_stage.py`. *Salida:* Etapa desacoplada del SDK.

### STORY-2.3B-04
- **TASK-2.3B-04.1** — Añadir test de contrato: FakeProvider con AnalysisRequest de ejemplo devuelve AnalysisResponse con campos requeridos; opcionalmente test con GeminiAnalysisProvider si es estable. *Salida:* Test que falle si el contrato se rompe.

### STORY-2.3B-05
- **TASK-2.3B-05.1** — Definir JobRepository (Protocol) en `src/application/ports/job_repository.py` (o jobs/contracts): create, get, update. *Salida:* Protocolo definido.
- **TASK-2.3B-05.2** — Implementar JobStoreAdapter en `src/jobs/adapters/` que implemente JobRepository delegando en create_job, get_job, update_job. **Clasificación: Migration Adapter** — el adapter envuelve job_store (Legacy Compatibility); job_store sigue siendo la implementación real hasta que se reemplace en una fase posterior. Documentar o nombrar la clase de forma que sea identificable como adapter de migración (ej. `JobStoreRepositoryAdapter`). *Salida:* Adapter usable en servicios.

### STORY-2.3B-06
- **TASK-2.3B-06.1** — Definir JobQueue (Protocol) en `src/application/ports/job_queue.py`: enqueue(job_id), dequeue(timeout) -> job_id | None. *Salida:* Protocolo definido.
- **TASK-2.3B-06.2** — Implementar InMemoryJobQueue en `src/infrastructure/queue/` o `src/jobs/adapters/` que delegue en la cola actual. **Clasificación: Migration Adapter** — envuelve la cola legacy; la cola existente sigue en uso. Identificable como adapter (ej. nombre o docstring). *Salida:* Adapter usable en CreateJobService y worker.

### STORY-2.3B-07
- **TASK-2.3B-07.1** — Test JobRepository: create luego get devuelve mismo job. *Salida:* Test de contrato.
- **TASK-2.3B-07.2** — Test JobQueue: enqueue luego dequeue devuelve mismo job_id; opcional timeout. *Salida:* Test de contrato.

### STORY-2.3B-08
- **TASK-2.3B-08.1** — Definir ArtifactStorage (Protocol): write_json, write_bytes, exists. *Salida:* Puerto en application/ports o pipeline/contracts.
- **TASK-2.3B-08.2** — Implementar FileSystemArtifactStorage que escriba bajo run_dir. **Clasificación: Target Architecture** (implementación concreta del puerto ArtifactStorage) o **Migration Adapter** si por ahora solo envuelve la escritura directa actual a Path; indicar en código. *Salida:* Implementación lista para inyección.

### STORY-2.3B-09
- **TASK-2.3B-09.1** — Revisar y endurecer DTOs entre etapas (PreparedInput, FrameBundleResult, RawAnalysisResult, ResolvedEntitiesResult, EvidenceResult, ReportingResult) en `src/pipeline/dto/` o en stages. *Salida:* Sin dict ambiguos entre etapas.
- **TASK-2.3B-09.2** — Refactorizar EvidenceStage y ReportingStage para recibir ArtifactStorage por constructor y usarlo para escribir JSON. *Salida:* Etapas desacopladas de escritura directa a disco.

### STORY-2.3B-10
- **TASK-2.3B-10.1** — (Opcional) Definir FrameCollectionRequest/FrameCollectionResult (o alinear con FramesBundle); adaptar VideoFrameSource y PhotosFrameSource al contrato. *Salida:* FrameSource con tipos claros.
- **TASK-2.3B-10.2** — (Opcional) Definir PromptBuilder y PromptPayload; extraer construcción del prompt a InventoryPromptBuilder. *Salida:* Contrato listo si se cumple Interface Creation Policy.

### STORY-2.3B-11
- **TASK-2.3B-11.1** — Refactorizar CreateJobService y ExecuteJobService para recibir JobRepository (y CreateJobService JobQueue) por constructor. *Salida:* Servicios dependen de puertos.
- **TASK-2.3B-11.2** — Refactorizar pipeline y etapas para recibir AnalysisProvider, ArtifactStorage, FrameSource (o factory) por constructor. *Salida:* Pipeline sin dependencias directas de implementaciones.
- **TASK-2.3B-11.3** — Crear compositor (bootstrap) en app o módulo dedicado: instanciar JobStoreAdapter, InMemoryJobQueue, FileSystemArtifactStorage, GeminiAnalysisProvider, etapas, pipeline, CreateJobService, ExecuteJobService; inyectar dependencias. *Archivos:* `src/app.py` o `src/bootstrap.py`. *Salida:* Un solo lugar de wiring; E2E pasando.

### STORY-2.3C-01
- **TASK-2.3C-01.1** — Definir RunRecord (dataclass o modelo) en `src/domain/run/models.py` o `src/jobs/models.py`: run_id, job_id, status, engine_version, schema_version, provider_name, provider_model, started_at, finished_at, duration_ms, effective_config_snapshot, warning_count, error_code, error_message. *Salida:* Tipo RunRecord importable.
- **TASK-2.3C-01.2** — Definir RunRepository (Protocol) en `src/application/ports/run_repository.py`: create_for_job(job_id, ...) -> RunRecord, get(run_id) -> RunRecord | None, mark_running(run_id), mark_succeeded(run_id, result_summary), mark_failed(run_id, error_code, error_message). *Salida:* Puerto definido.
- **TASK-2.3C-01.3** — Implementar RunRepository concreto (ej. SqlRunRepository) que persista en tabla `runs`; cuando sqlserver_enabled es false, implementación in-memory o no-op que permita seguir operando sin DB. *Módulo sugerido:* `src/database/run_repository.py` o `src/infrastructure/persistence/`. *Salida:* Run creado y actualizado en DB cuando está habilitada.

### STORY-2.3C-02
- **TASK-2.3C-02.1** — Definir RunErrorRecord en `src/domain/run/models.py` (o mismo módulo que RunRecord): run_id, stage_name, error_code, error_type, message, details, retriable, occurred_at. *Salida:* Tipo RunErrorRecord.
- **TASK-2.3C-02.2** — Definir RunErrorRepository (Protocol): save(error: RunErrorRecord). *Salida:* Puerto en `src/application/ports/run_error_repository.py`.
- **TASK-2.3C-02.3** — Implementar RunErrorRepository que persista en tabla `run_errors`; cuando DB no está habilitada, implementación no-op o en memoria. *Módulo sugerido:* `src/database/run_error_repository.py`. *Salida:* Errores persistidos en cada fallo de ejecución.

### STORY-2.3C-03
- **TASK-2.3C-03.1** — Definir RunStageExecutionRecord: run_id, stage_name, status, started_at, finished_at, duration_ms, input_summary, output_summary, warning_count, error_message. *Salida:* Tipo definido.
- **TASK-2.3C-03.2** — Definir RunStageRepository (Protocol): save(record: RunStageExecutionRecord). Implementar persistencia en tabla `run_stage_executions`. *Módulo sugerido:* `src/database/run_stage_repository.py`. *Salida:* Repositorio usable desde orquestador o ExecuteJobService.
- **TASK-2.3C-03.3** — Definir RunArtifactRecord: run_id, artifact_type, artifact_ref, content_type, metadata. Definir RunArtifactRepository (Protocol): save(record), list_by_run(run_id). Implementar persistencia en tabla `run_artifacts`. *Módulo sugerido:* `src/database/run_artifact_repository.py`. *Salida:* Artifacts referenciados desde DB.

### STORY-2.3C-04
- **TASK-2.3C-04.1** — Refactorizar ExecuteJobService: al inicio de execute(job_id), crear Run vía run_repository.create_for_job(job_id) y marcar RUNNING con mark_running(run_id). *Archivos:* `src/application/services/execute_job_service.py`. *Salida:* Run creado y en RUNNING antes de invocar pipeline.
- **TASK-2.3C-04.2** — Tras ejecución exitosa del pipeline: obtener ResolvedEntitiesResult y ReportingResult del flujo; persistir resultado estructurado (entidades, resumen, rutas de artifacts) en runs y tablas relacionadas (run_entities o columnas de resumen en runs); llamar run_repository.mark_succeeded(run_id, result_summary). No leer hybrid_report.json para rellenar DB; usar solo DTOs. *Salida:* Fuente de verdad en DB; JSON como artifact derivado.
- **TASK-2.3C-04.3** — En excepción o fallo: crear RunErrorRecord con run_id, stage_name, error_code, message; llamar run_error_repository.save(error); llamar run_repository.mark_failed(run_id, error_code, message); actualizar job a FAILED. *Salida:* Todo fallo produce RunErrorRecord y run/job en FAILED.
- **TASK-2.3C-04.4** — Implementar semántica PARTIAL: si la persistencia estructurada tuvo éxito pero la generación de un artifact (p. ej. hybrid_report.json) falla, marcar run como PARTIAL (o FAILED según criterio de diseño) y registrar error en RunErrorRecord. *Salida:* Cumplimiento de Run Status Semantics.

### STORY-2.3C-05
- **TASK-2.3C-05.1** — Test: run creado y marcado RUNNING al iniciar execute(job_id). *Salida:* Test que verifica create_for_job y mark_running.
- **TASK-2.3C-05.2** — Test: pipeline termina con éxito → resultado estructurado persistido en runs/run_entities (o equivalente) y run marcado SUCCEEDED. Verificar que los datos no provienen solo de JSON. *Salida:* Test de persistencia desde DTOs.
- **TASK-2.3C-05.3** — Test: pipeline o provider lanza excepción → RunErrorRecord persistido, run y job en FAILED. *Salida:* Test de manejo de fallos y invariante "todos los errores producen RunErrorRecord".

### STORY-2.3C-06
- **TASK-2.3C-06.1** — Crear módulo o helper de logging estructurado (ej. `src/utils/structured_logging.py`): función o wrapper que reciba logger, job_id, run_id, stage (opcional) y emita logs con esos campos en `extra`. *Salida:* Helper reutilizable.
- **TASK-2.3C-06.2** — Usar el helper en ExecuteJobService y en el orquestador/etapas del pipeline para que cada log relevante incluya job_id y run_id (y stage cuando aplique). *Archivos:* `src/application/services/execute_job_service.py`, `src/pipeline/hybrid_inventory_pipeline.py` o etapas. *Salida:* Logs filtrables por run.

### STORY-2.3C-07
- **TASK-2.3C-07.1** — Definir estructura de run_manifest.json (run_id, job_id, engine_version, provider, input summary, frames count, stages, warnings, artifact refs, result_summary). *Salida:* Esquema o dataclass documentado.
- **TASK-2.3C-07.2** — Generar y escribir run_manifest.json en run_dir al finalizar el run (éxito o fallo), usando RunContext y DTOs disponibles. *Módulo sugerido:* dentro de ExecuteJobService o colaborador dedicado; escribir vía ArtifactStorage si está inyectado. *Salida:* run_manifest.json presente en run_dir.
- **TASK-2.3C-07.3** — Opcional: registrar el artifact en RunArtifactRepository (tipo "run_manifest", artifact_ref = ruta relativa). Instrumentar orquestador o etapas para persistir RunStageExecutionRecord por etapa (started_at, finished_at, duration_ms, resumen) vía RunStageRepository. *Salida:* Trazabilidad por etapa en DB si se implementa.

### STORY-2.3C-08
- **TASK-2.3C-08.1** — Documentar en docs/ o README que la API y el worker son componentes separables: la API sirve requests; el worker consume la cola y ejecuta jobs vía ExecuteJobService. *Salida:* Documentación actualizada.
- **TASK-2.3C-08.2** — Opcional: implementar entrypoint `python -m src.worker` (o `src.worker:main`) que ejecute solo el loop de cola (dequeue → execute_job_service.execute) sin arrancar uvicorn. *Archivos:* `src/worker.py` o `src/jobs/worker.py` con `if __name__ == "__main__"`. *Salida:* Worker ejecutable como proceso independiente.

### STORY-2.3C-09
- **TASK-2.3C-09.1** — Crear scripts o migraciones SQL para tablas `runs`, `run_errors`, `run_stage_executions`, `run_artifacts` (y `run_entities` si se persisten entidades por run). *Módulo sugerido:* `migrations/` o `scripts/schema/`. *Salida:* Migraciones aplicables en entornos con DB.
- **TASK-2.3C-09.2** — Documentar y probar comportamiento cuando sqlserver_enabled es false: Run en memoria o solo run_manifest.json; RunErrorRepository y RunRepository con implementación no-op o in-memory para no fallar. *Salida:* Sistema operativo sin DB; documentación de modo "solo FS".

---

## 6. Orden recomendado de implementación

### Prerrequisitos
- **Baseline pipeline smoke test:** Antes de iniciar la extracción de etapas, debe existir y estar en verde un test de humo que ejecute el pipeline actual de punta a punta y valide salida mínima válida (véase **Baseline Pipeline Smoke Test** en la sección de EPIC-2.3A-02). Este test debe permanecer en verde durante todo 2.3.A.
- **TASK-2.3A-01.1, TASK-2.3A-02.1** deben estar hechos antes de cualquier etapa.
- **STORY-2.3A-03 a STORY-2.3A-07** se implementan **en secuencia**, no en paralelo, según la **Pipeline Stage Extraction Strategy**: cada extracción modifica el mismo núcleo de orquestación; el pipeline debe quedar ejecutable después de cada una antes de pasar a la siguiente (véase orden recomendado más abajo).
- **STORY-2.3A-09** es independiente del pipeline; puede desarrollarse en paralelo a la secuencia de etapas (03→04→05→06→07) si se desea.

### Secuencia sugerida
1. **Baseline smoke test:** Introducir o formalizar el test de humo del pipeline antes de refactor (prerrequisito de 2).
2. **RunContext y contrato de etapa:** TASK-2.3A-01.1, TASK-2.3A-02.1 (STORY-2.3A-01, STORY-2.3A-02).
3. **Extracción de etapas (estrictamente secuencial):** STORY-2.3A-03 → 04 → 05 → 06 → 07. Tras cada una, ejecutar baseline smoke test y dejar pipeline en estado runnable antes de la siguiente. No iniciar la siguiente extracción en otra rama en paralelo.
4. **Orquestador:** STORY-2.3A-08 (depende de 03–07 completadas).
5. **CreateJobService y endpoint:** STORY-2.3A-09, STORY-2.3A-10 (pueden solaparse con 3–4 si se respeta la secuencia de etapas).
6. **ExecuteJobService y worker:** STORY-2.3A-11, STORY-2.3A-12 (dependen de STORY-2.3A-08).
7. **Tests de integración:** STORY-2.3A-13 (después de 10 y 12).

### No iniciar pronto
- **Historias 2.3.B** que cambien AnalysisStage o orquestador antes de tener las etapas estables (STORY-2.3A-08 cerrada).
- **Historias 2.3.C** de persistencia de Run/errores hasta que los servicios dependan de puertos (2.3.B compositor y servicios inyectados).

### Retrasar hasta que los contratos estén estables
- Refactorizar EvidenceStage/ReportingStage a ArtifactStorage (STORY-2.3B-09) hasta tener ArtifactStorage definido e inyectado.
- Persistencia de resultado desde DTOs (STORY-2.3C-04) hasta tener DTOs definitivos y RunRepository/RunErrorRepository listos.

### Minimizar regresión
- El **baseline pipeline smoke test** debe ejecutarse después de cada extracción de etapa (03–07) y permanecer en verde; no avanzar a la siguiente etapa si falla.
- Después de STORY-2.3A-08 y de STORY-2.3A-12, ejecutar E2E completo antes de seguir con 2.3.B.

---

## 7. Primer slice de implementación recomendado

### Objetivo del primer slice
Poner en marcha 2.3 con el menor riesgo y la mayor ganancia inmediata: **Baseline pipeline smoke test en verde + RunContext + contrato de etapa + una sola etapa extraída + pipeline que ya use RunContext internamente**, sin aún tocar endpoint ni worker.

### Historias del primer slice
0. **Baseline pipeline smoke test** — Introducir o formalizar un test que ejecute el pipeline actual de punta a punta y valide salida mínima válida; debe estar en verde antes de tocar _run_hybrid y permanecer en verde durante todo el slice (véase **Baseline Pipeline Smoke Test** en EPIC-2.3A-02).
1. **STORY-2.3A-01** — Introduce RunContext.
2. **STORY-2.3A-02** — Define PipelineStage protocol.
3. **STORY-2.3A-03** — Extract InputPreparationStage (primera etapa).
4. **STORY-2.3A-08 (parcial)** — Refactor mínimo del pipeline: construir RunContext dentro del flujo actual (donde hoy se pasan parámetros), invocar InputPreparationStage.run(context, None) y usar su resultado en el resto de _run_hybrid que sigue en línea; no extraer aún el resto de etapas.

### Por qué este slice
- Introduce el concepto RunContext y el contrato de etapa sin mover todo el flujo de golpe.
- Una sola etapa extraída demuestra el patrón y valida que PreparedInput → siguiente fase funciona.
- El pipeline sigue funcionando; el resto de _run_hybrid sigue en línea hasta el siguiente slice.
- No se tocan API ni worker; no hay riesgo de regresión en rutas o cola.

### Qué dejar intacto en el primer slice
- Endpoints y worker (no tocar STORY-2.3A-10, 2.3A-11, 2.3A-12).
- Resto de etapas (FrameAcquisition, Analysis, EntityResolution, Evidence, Reporting) siguen como bloque dentro de _run_hybrid.
- job_store, queue, CreateJobService, ExecuteJobService.

### Cómo mantener operabilidad
- Ejecutar tests E2E o humo antes y después del slice.
- Mantener la misma firma pública del pipeline (process_video o la que use el worker) que recibe los parámetros actuales; internamente el pipeline puede construir RunContext a partir de esos parámetros y pasarlo a InputPreparationStage y al bloque restante.

### Siguiente slice recomendado
Extraer FrameAcquisitionStage (STORY-2.3A-04) y conectar InputPreparationStage → FrameAcquisitionStage en el orquestador; luego AnalysisStage (2.3A-05), y así sucesivamente hasta cerrar STORY-2.3A-08 completo. Después, CreateJobService y endpoint (2.3A-09, 2.3A-10), luego ExecuteJobService y worker (2.3A-11, 2.3A-12), y por último tests de integración (2.3A-13).

---

## 8. Quick wins

- **RunContext solo (sin extraer etapas aún):** Introducir RunContext y usarlo dentro del pipeline actual pasando context en lugar de muchos kwargs; reduce parámetros y prepara el terreno. Bajo costo, alto impacto en claridad. *Plan §9.*
- **JobQueue como interfaz temprano:** Definir JobQueue y envolver la cola actual en InMemoryJobQueue; que el worker y CreateJobService dependan del puerto. Permite testear con doble y prepara cola persistente. *Plan §9.*
- **DTO RawAnalysisResult en AnalysisStage:** Definir RawAnalysisResult (parsed_json, provider_name) y que AnalysisStage lo devuelva; EntityResolutionStage lo recibe tipado. Reduce acoplamiento con el SDK sin tocar aún el resto de etapas. *Plan §9.*
- **run_manifest.json mínimo:** Escribir manifest mínimo (run_id, job_id, provider, frame_count, report_path) al finalizar el run, sin necesidad de todas las tablas de runs. Mejora trazabilidad con poco esfuerzo. *Plan §9.*
- **Logging con job_id/run_id:** Helper que inyecte job_id y run_id en logger.info(..., extra={...}) en worker y pipeline. Mejora operación sin cambiar modelo de datos. *Plan §9.*

---

## 9. Riesgos de ejecución

| Riesgo | Mitigación |
|--------|------------|
| **Regresión funcional** al extraer etapas (p. ej. frame indices truncados) | Tests E2E antes del refactor; ejecutar mismos casos después de cada extracción; comparar reportes en tests si es posible. |
| **Architecture drift** (volver a acoplar pipeline a Gemini o job_store) | Definition of Done global: pipeline y etapas solo dependen de puertos o DTOs; worker sin lógica de negocio. Revisión de PR enfocada en dependencias. |
| **Sobrediseño / over-abstraction** | Interface Creation Policy: interfaz solo si hay más de una implementación, necesidad de mock en tests, o variabilidad acordada. No introducir puertos “por si acaso”. |
| **Migración inconsistente** (parte en JSON, parte en DB) | Operational Consistency Rules; en 2.3.C persistir siempre desde DTOs y marcar run SUCCEEDED solo tras persistir resultado estructurado. |
| **Persistencia incompleta** (SUCCEEDED sin datos en DB) | Invariante explícito en DoD y tests de ciclo de vida: run SUCCEEDED ⇒ datos en runs/run_entities; tests que lo comprueben. |
| **Testing gaps** (contratos sin tests, E2E frágil) | Requisitos de testing por etapa (plan §8): stage unit tests, E2E smoke, contract tests para providers/repos/queue, run lifecycle y failure handling en 2.3.C. |
| **Compatibilidad sin DB** en 2.3.C | Run y errores opcionales cuando sqlserver_enabled es false; run_manifest.json y logs estructurados pueden existir siempre. Probar modo “solo FS”. |
| **Rendimiento** por más escrituras (runs, stages, errors) | Medir flujo típico antes/después; inserciones mínimas necesarias; batch para muchas entidades si aplica. |

---

## 10. Definition of Ready por historia

- **Módulos afectados identificados:** Lista de archivos/módulos que la historia toca (p. ej. hybrid_inventory_pipeline.py, stages/, application/services/).
- **Comportamiento actual entendido:** Si es refactor, descripción breve de cómo funciona hoy el flujo y qué no debe cambiar observablemente.
- **Tests seleccionados:** Qué tests existentes se ejecutarán para validar (E2E, unit de etapa, contract); si hace falta nuevo test, está definido.
- **Dependencias ya merged:** Las historias de las que depende (por ID) están completadas y en rama principal o feature branch acordado.
- **Contratos/ interfaces estables (si aplica):** Si la historia implementa un adapter o una etapa, los protocolos/DTOs que debe cumplir ya están definidos y aceptados.

---

## 11. Definition of Done por historia

- **Comportamiento preservado:** No hay cambio funcional observable en API ni en formato del reporte, salvo que la historia sea explícitamente de cambio de contrato.
- **Tests pasando:** Tests unitarios/integración/contract asociados a la historia pasan; E2E existentes siguen pasando si la historia afecta flujo completo; en 2.3.A el baseline pipeline smoke test debe permanecer en verde.
- **Sin dependencia directa de infra prohibida:** Si el plan prohíbe que el pipeline dependa de implementaciones concretas (Gemini, job_store, queue, filesystem directo), la historia no introduce esas dependencias.
- **Documentación actualizada:** Cambios en contratos, puertos o flujo reflejados en docstrings, README o docs cuando sea relevante.
- **Criterios de aceptación de la historia cumplidos:** Cada AC de la historia verificable y cumplido.

**Restricciones arquitectónicas (DoD global de 2.3, aplicables al cierre de la versión y como guía en cada historia):**

- **Orquestación del pipeline:** El pipeline (orquestador y etapas) no debe depender de implementaciones concretas de infraestructura (Gemini, job_store, queue, filesystem directo); solo de puertos (AnalysisProvider, JobRepository, JobQueue, ArtifactStorage, etc.) o de DTOs.
- **Worker sin lógica de negocio:** El worker no debe contener lógica de negocio; solo obtener job_id de la cola, llamar a ExecuteJobService.execute(job_id), y preocupaciones de proceso (loop, shutdown). No debe cargar job, construir RunContext, actualizar estado ni empujar resultados a DB.
- **Etapas con resultados explícitos:** Las etapas del pipeline deben devolver objetos de resultado tipados (PreparedInput, FrameBundleResult, RawAnalysisResult, etc.); el flujo de datos entre etapas es por valores de retorno, no por mutación de RunContext ni por dict ambiguos.
- **Run por ejecución:** Cada invocación del pipeline (vía ExecuteJobService) debe crear y persistir un registro Run (cuando DB está habilitada) o al menos producir run_manifest.json / Run en memoria cuando no hay DB, de forma que cada ejecución sea identificable y auditable.
- **Resultados persistidos estructuralmente:** El resultado del run (entidades, resumen, referencias a artifacts) debe escribirse en la base de datos (o fuente de verdad acordada) desde los DTOs producidos por el pipeline, no re-parseando archivos JSON.
- **Logs con job_id y run_id:** Cada log emitido durante la ejecución del job (pipeline y ExecuteJobService) debe incluir job_id y run_id en forma estructurada (p. ej. logger.info(..., extra={"job_id": ..., "run_id": ...})) para que los logs sean filtrables y trazables por run.
- **Adapters de migración identificables:** Los componentes que envuelven legacy (p. ej. JobRepositoryAdapter sobre job_store) deben estar claramente identificados como adapters de migración (nombre, documentación o convención) para que en el futuro se pueda reemplazar el legacy sin ambigüedad.

---

## 12. Backlog priorizado inicial

| Prioridad | Story ID | Título | Stage | Motivo de prioridad |
|-----------|-----------|--------|-------|----------------------|
| 1 | STORY-2.3A-01 | Introduce RunContext | 2.3.A | Base de todo el refactor del pipeline; sin bloqueos. |
| 2 | STORY-2.3A-02 | Define PipelineStage protocol | 2.3.A | Necesario para extraer etapas; depende solo de 2.3A-01. |
| 3 | STORY-2.3A-03 | Extract InputPreparationStage | 2.3.A | Primera etapa; valida el patrón y RunContext. |
| 4 | STORY-2.3A-08 | Refactor pipeline to orchestrate stages | 2.3.A | Integra etapas y RunContext; habilitador de ExecuteJobService. Puede ser parcial en primer slice (solo InputPreparation + resto en línea). |
| 5 | STORY-2.3A-04 | Extract FrameAcquisitionStage | 2.3.A | Siguiente etapa en cadena; alta sensibilidad a regresión, hacer con tests. |
| 6 | STORY-2.3A-05 | Extract AnalysisStage | 2.3.A | Siguiente en cadena; base para 2.3.B AnalysisProvider. |
| 7 | STORY-2.3A-06 | Extract EntityResolutionStage | 2.3.A | Siguiente en cadena. |
| 8 | STORY-2.3A-07 | Extract EvidenceStage and ReportingStage | 2.3.A | Cierra la cadena de etapas. |
| 9 | STORY-2.3A-09 | Implement CreateJobService | 2.3.A | Independiente del pipeline; permite afinar endpoint. |
| 10 | STORY-2.3A-10 | Refactor POST /jobs to CreateJobService | 2.3.A | Endpoint fino; depende de 2.3A-09. |
| 11 | STORY-2.3A-11 | Implement ExecuteJobService | 2.3.A | Caso de uso de ejecución; depende de pipeline con RunContext. |
| 12 | STORY-2.3A-12 | Refactor worker to ExecuteJobService | 2.3.A | Worker fino; depende de 2.3A-11. |
| 13 | STORY-2.3A-13 | Integration tests full flow | 2.3.A | Cierra 2.3.A con guarda de regresión. |
| 14 | STORY-2.3B-01 | Define AnalysisProvider port and DTOs | 2.3.B | Base para desacoplar Gemini. |
| 15 | STORY-2.3B-02 a 2.3B-04 | GeminiAnalysisProvider + AnalysisStage + contract tests | 2.3.B | Completa AnalysisProvider. |
| 16 | STORY-2.3B-05, 2.3B-06 | JobRepository and JobQueue | 2.3.B | Puertos de persistencia y cola. |
| 17 | STORY-2.3B-07 | Contract tests JobRepository/JobQueue | 2.3.B | Estabilidad de contratos. |
| 18 | STORY-2.3B-08, 2.3B-09 | ArtifactStorage and stage DTOs | 2.3.B | Escritura de artifacts y DTOs endurecidos. |
| 19 | STORY-2.3B-11 | Composition root and DI | 2.3.B | Sistema corriendo por puertos. |
| 20 | STORY-2.3C-01 a 2.3C-05 | Run lifecycle and persistence | 2.3.C | Fuente de verdad en DB. |
| 21 | STORY-2.3C-06, 2.3C-07 | Structured logging and run_manifest | 2.3.C | Observabilidad. |
| 22 | STORY-2.3C-08, 2.3C-09 | API/worker separation, migrations | 2.3.C | Operación y despliegue. |

---

## Recomendación final de arranque

**Primer movimiento recomendado:** Implementar **STORY-2.3A-01** (RunContext) y **STORY-2.3A-02** (PipelineStage)** en ese orden. A continuación, **STORY-2.3A-03** (InputPreparationStage)** y un refactor mínimo del pipeline para que construya RunContext y llame a InputPreparationStage.run(context, None), usando su resultado en el resto de _run_hybrid que sigue en línea. Con esto se valida RunContext y el patrón de etapas sin mover el resto del flujo, se mantiene el sistema operativo y se reduce el riesgo de regresión. A partir de ahí, seguir con la extracción de etapas una a una (2.3A-04 → 05 → 06 → 07) y luego el orquestador completo (2.3A-08), CreateJobService (2.3A-09), endpoint (2.3A-10), ExecuteJobService (2.3A-11), worker (2.3A-12) y tests de integración (2.3A-13). No iniciar 2.3.B hasta tener 2.3.A cerrado con E2E en verde; no iniciar 2.3.C hasta tener contratos y compositor de 2.3.B estables.
